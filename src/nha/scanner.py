# src/nha/scanner.py
from __future__ import annotations
import ipaddress, os, re, shutil, socket, subprocess, time, json
from typing import Dict, List, Set, Callable, Iterator, Tuple, Optional
from pathlib import Path

from .config import load_config
from .logger import get_logger
from .registry import record_many
from src.integrations.deco_config import known_nodes_from_config
from src.integrations.deco import detect_on_lan
from src.integrations.deco_api import fetch_clients

log = get_logger("nha")
DATA_DIR = Path("./data")

ProgressCb = Optional[Callable[[str, int, int, str], None]]
# cb(stage, done, total, note)

# --------------------- helpers ---------------------

def _cidr_hosts(cidr: str) -> List[str]:
    net = ipaddress.ip_network(cidr, strict=False)
    return [str(h) for h in net.hosts()]

def _nmap_path() -> str | None:
    return shutil.which("nmap")

def _run(cmd: List[str], timeout: int = 30) -> str:
    return subprocess.check_output(cmd, text=True, timeout=timeout, stderr=subprocess.STDOUT)

def _parse_arp_table() -> Dict[str, str]:
    out: Dict[str, str] = {}
    try:
        if os.name == "nt":
            txt = _run(["arp","-a"], timeout=10)
            for line in txt.splitlines():
                m = re.search(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F\-]{17})", line)
                if m:
                    ip, mac = m.group(1), m.group(2).lower().replace("-",":")
                    out[ip] = mac
        else:
            txt = _run(["arp","-an"], timeout=10)
            for line in txt.splitlines():
                m = re.search(r"\((\d+\.\d+\.\d+\.\d+)\)\s+at\s+([0-9a-fA-F:]{17})", line)
                if m:
                    ip, mac = m.group(1), m.group(2).lower()
                    out[ip] = mac
    except Exception:
        pass
    return out

# ------------------ discovery passes ----------------

def discover_nmap(cidr: str) -> Set[str]:
    nmap = _nmap_path()
    if not nmap: return set()
    try:
        args = [nmap, "-sn", "-PE", "-PA80,443,22,139,445,554,9100", cidr, "-oG", "-"]
        txt = _run(args, timeout=90)
        ips: Set[str] = set()
        for line in txt.splitlines():
            m = re.search(r"Host:\s+(\d+\.\d+\.\d+\.\d+)", line)
            if m: ips.add(m.group(1))
        return ips
    except Exception as e:
        log.warning("nmap discovery failed: %s", e)
        return set()

def discover_icmp_tcp(cidr: str, timeout_ms: int = 400, cb: ProgressCb = None) -> Set[str]:
    ips = _cidr_hosts(cidr); found: Set[str] = set()
    total = len(ips)
    for i, ip in enumerate(ips, 1):
        try:
            if os.name == "nt":
                rc = subprocess.call(["ping","-n","1","-w",str(timeout_ms), ip],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                rc = subprocess.call(["ping","-c","1","-W",str(max(1, timeout_ms//1000)), ip],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if rc == 0: found.add(ip)
        except Exception: pass
        if cb and (i % 16 == 0 or i == total):
            cb("icmp", i, total, ip)
    # one TCP probe for non-responders
    remain = [ip for ip in ips if ip not in found]
    total2 = len(remain)
    for j, ip in enumerate(remain, 1):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.settimeout(timeout_ms/1000.0)
            if s.connect_ex((ip,80)) == 0: found.add(ip)
            s.close()
        except Exception: pass
        if cb and (j % 16 == 0 or j == total2):
            cb("tcp", j, total2, ip)
    return found

def discover_ssdp(timeout_s: float = 2.0) -> Set[str]:
    MCAST_GRP = "239.255.255.250"; MCAST_PORT = 1900
    req = "\r\n".join([
        "M-SEARCH * HTTP/1.1",
        f"HOST: {MCAST_GRP}:{MCAST_PORT}",
        "MAN: \"ssdp:discover\"",
        "MX: 1",
        "ST: ssdp:all", "", ""]).encode("ascii")
    ips: Set[str] = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        s.settimeout(timeout_s)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        s.sendto(req, (MCAST_GRP, MCAST_PORT))
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            try:
                _data, (rip, _rport) = s.recvfrom(2048)
                ips.add(rip)
            except socket.timeout:
                break
        s.close()
    except Exception:
        pass
    return ips

def discover_mdns(timeout_s: float = 2.0) -> Set[str]:
    MCAST_GRP = "224.0.0.251"; MCAST_PORT = 5353
    qname = b"\x09_services\x07_dns-sd\x04_udp\x05local\x00"
    q = b"\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00" + qname + b"\x00\x0c\x00\x01"
    ips: Set[str] = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        s.settimeout(timeout_s)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
        s.sendto(q, (MCAST_GRP, MCAST_PORT))
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            try:
                _data, (rip, _rport) = s.recvfrom(2048)
                ips.add(rip)
            except socket.timeout:
                break
        s.close()
    except Exception:
        pass
    return ips

# -------------------- progressive scan --------------------

def run_scan_iter(progress: ProgressCb = None) -> Iterator[Tuple[str, dict]]:
    """
    Generator that yields step markers for UI progress.
    Yields ('stage', payload) where stage in:
      'begin','arp','nmap','icmp_tcp','ssdp','mdns','deco_mark','deco_merge','save','record','done'
    """
    cfg = load_config()
    cidr = (cfg.get("network",{})).get("cidr", "192.168.1.0/24")
    segment = cidr
    yield ("begin", {"cidr": cidr})

    sources_map: Dict[str, List[str]] = {}

    # ARP
    arp = _parse_arp_table()
    for ip in arp: sources_map.setdefault(ip, []).append("arp")
    yield ("arp", {"count": len(arp)})

    # nmap
    nm_ips = discover_nmap(cidr) if _nmap_path() else set()
    for ip in nm_ips: sources_map.setdefault(ip, []).append("nmap")
    yield ("nmap", {"count": len(nm_ips)})

    # icmp/tcp with per-16 host progress
    icmp_ips = discover_icmp_tcp(cidr, cb=progress)
    for ip in icmp_ips: sources_map.setdefault(ip, []).append("icmp/tcp")
    yield ("icmp_tcp", {"count": len(icmp_ips)})

    # ssdp
    ssdp_ips = discover_ssdp()
    for ip in ssdp_ips: sources_map.setdefault(ip, []).append("ssdp")
    yield ("ssdp", {"count": len(ssdp_ips)})

    # mdns
    mdns_ips = discover_mdns()
    for ip in mdns_ips: sources_map.setdefault(ip, []).append("mdns")
    yield ("mdns", {"count": len(mdns_ips)})

    # union & base rows
    all_ips = set(sources_map.keys())
    known_deco_nodes = known_nodes_from_config(cfg)
    if known_deco_nodes:
        arp_mac_to_ip = {mac: ip for ip, mac in arp.items() if mac}
        try:
            net = ipaddress.ip_network(cidr, strict=False)
        except Exception:
            net = None
        for node_ip, node in known_deco_nodes.items():
            node_mac = node.get("mac") or ""
            arp_ip = arp_mac_to_ip.get(node_mac)
            include_ip = node_ip if node_ip in all_ips else arp_ip
            if not include_ip:
                continue
            if net is not None and ipaddress.ip_address(include_ip) not in net:
                continue
            all_ips.add(include_ip)
            sources_map.setdefault(include_ip, []).append("deco-config")

    devices: List[Dict[str, str]] = []
    for ip in sorted(all_ips, key=lambda s: tuple(int(x) for x in s.split("."))):
        d: Dict[str,str] = {"ip": ip}
        mac = arp.get(ip, "")
        if mac: d["mac"] = mac
        node = known_deco_nodes.get(ip)
        if not node and mac:
            node = next((n for n in known_deco_nodes.values() if n.get("mac") == mac), None)
        if node:
            d.setdefault("mac", node.get("mac") or "")
            d.setdefault("vendor", "TP-Link")
            d.setdefault("category", "Router/AP")
            if node.get("name"):
                d.setdefault("hostname", node["name"])
            if node.get("model"):
                d.setdefault("model", node["model"])
        devices.append(d)

    # deco mark (fingerprint APs)
    try:
        deco_info = detect_on_lan(list(all_ips))
    except Exception as e:
        log.warning("Deco detection failed: %s", e)
        deco_info = {}
    if deco_info:
        for d in devices:
            ip = d.get("ip")
            meta = deco_info.get(ip)
            if not meta: continue
            if meta.get("is_deco"):
                d.setdefault("vendor", "TP-Link")
                d.setdefault("category", "Router/AP")
                fn = meta.get("friendly_name");  model = meta.get("model")
                if fn: d.setdefault("hostname", fn)
                if model: d.setdefault("model", model)
                ev = [f"deco:{e}" for e in (meta.get("evidence") or [])]
                if ev:
                    d.setdefault("issues", [])
                    if isinstance(d["issues"], list): d["issues"] = list(set(d["issues"] + ev))
                    else: d["issues"] = ev
    yield ("deco_mark", {"count": len([1 for d in devices if d.get('category')=='Router/AP'])})

    # deco merge (controller clients)
    try:
        deco_cfg = (cfg.get("integrations", {}) or {}).get("deco", {}) or {}
        do_import = deco_cfg.get("enabled") and deco_cfg.get("auto_import_on_scan", False)
        deco_clients = fetch_clients(deco_cfg) if do_import else []
    except Exception as e:
        log.warning("Deco API fetch failed: %s", e)
        deco_clients = []
    if deco_clients:
        by_ip = {d.get("ip"): d for d in devices if d.get("ip")}
        for c in deco_clients:
            ip = c.get("ip")
            if not ip: continue
            if ip in by_ip:
                d = by_ip[ip]
                if c.get("mac"): d["mac"] = (c["mac"] or "").lower()
                if c.get("hostname") and not d.get("hostname"): d["hostname"] = c["hostname"]
                if c.get("vendor") and not d.get("vendor"):     d["vendor"]   = c["vendor"]
                if c.get("ssid"):        d["ssid"]   = c["ssid"]
                if c.get("vlan_id") is not None: d["vlan_id"] = c["vlan_id"]
                if c.get("ap_mac"):      d["ap_mac"] = (c["ap_mac"] or "").lower()
                if c.get("band"):        d["band"] = c["band"]
                sources_map.setdefault(ip, []).append("deco-api")
            else:
                nd: Dict[str,str] = {
                    "ip": ip,
                    "mac": (c.get("mac") or "").lower(),
                    "hostname": c.get("hostname") or "",
                    "vendor": c.get("vendor") or ""
                }
                if c.get("ssid"): nd["ssid"] = c["ssid"]
                if c.get("vlan_id") is not None: nd["vlan_id"] = c["vlan_id"]  # type: ignore[assignment]
                if c.get("ap_mac"): nd["ap_mac"] = (c["ap_mac"] or "").lower()
                if c.get("band"): nd["band"] = c["band"]
                devices.append(nd)
                sources_map.setdefault(ip, []).append("deco-api")
    yield ("deco_merge", {"count": len(deco_clients)})

    # save + record
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "current_scan.json").write_text(json.dumps(devices, indent=2), encoding="utf-8")
    yield ("save", {"path": str((DATA_DIR / 'current_scan.json').resolve())})

    record_many(devices, segment, sources_map)
    yield ("record", {"segment": segment, "total": len(devices)})

    log.info("scan: %d devices → %s", len(devices), DATA_DIR / "current_scan.json")
    yield ("done", {"total": len(devices)})

def run_scan() -> List[Dict[str, str]]:
    """
    Back-compat wrapper: run full scan synchronously and return devices.
    """
    last_payload: Dict[str, object] = {}
    for _stage, payload in run_scan_iter():
        last_payload = payload
    # Return parsed file to avoid duplication
    try:
        return json.loads((DATA_DIR / "current_scan.json").read_text(encoding="utf-8"))
    except Exception:
        return []
