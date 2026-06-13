#!/usr/bin/env python3
# @capability: deco_mesh_diagnostics
# @domain: network_diagnostics
# @maturity: prototype
# @extraction_ready: false

from __future__ import annotations

import argparse
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.integrations.deco_api import fetch_clients
from src.integrations.deco_config import known_nodes_from_config, normalize_mac
from src.nha.config import load_config


DEFAULT_DECO_NODES = {
    "192.168.1.189": {"name": "Study", "ip": "192.168.1.189", "mac": "1c:3b:f3:55:02:39"},
    "192.168.1.246": {"name": "Bedroom", "ip": "192.168.1.246", "mac": "1c:3b:f3:54:fe:9c"},
    "192.168.1.149": {"name": "Garage", "ip": "192.168.1.149", "mac": "1c:3b:f3:48:6b:c0"},
    "192.168.1.216": {"name": "Garden", "ip": "192.168.1.216", "mac": "50:3d:d1:a7:ed:54"},
}


def _run(cmd: List[str], timeout: int = 10) -> str:
    return subprocess.check_output(cmd, text=True, encoding="utf-8", errors="replace", timeout=timeout)


def _find_gateway() -> Optional[str]:
    try:
        txt = _run(["ipconfig"], timeout=10) if os.name == "nt" else _run(["ip", "route"], timeout=10)
    except Exception:
        return None

    if os.name == "nt":
        for line in txt.splitlines():
            if "Default Gateway" in line and "." in line:
                value = line.split(":", 1)[-1].strip()
                if value.count(".") == 3:
                    return value
    else:
        m = re.search(r"\bdefault\s+via\s+(\d+\.\d+\.\d+\.\d+)", txt)
        if m:
            return m.group(1)
    return None


def _arp_table() -> Dict[str, str]:
    out: Dict[str, str] = {}
    try:
        txt = _run(["arp", "-a"], timeout=8) if os.name == "nt" else _run(["arp", "-an"], timeout=8)
    except Exception:
        return out

    if os.name == "nt":
        pat = r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F\-]{17})"
    else:
        pat = r"\((\d+\.\d+\.\d+\.\d+)\)\s+at\s+([0-9a-fA-F:]{17})"
    for line in txt.splitlines():
        m = re.search(pat, line)
        if m:
            out[m.group(1)] = normalize_mac(m.group(2))
    return out


def discover_live(cidr: str, max_hosts: int = 254) -> List[str]:
    live = set(_arp_table().keys())
    try:
        net = ipaddress.ip_network(cidr, strict=False)
    except Exception:
        return sorted(live)

    arp_set = {ip for ip in live if ipaddress.ip_address(ip) in net}
    for ip in [str(h) for h in net.hosts()][:max_hosts]:
        if ip in arp_set:
            continue
        try:
            if os.name == "nt":
                cmd = ["ping", "-n", "1", "-w", "80", ip]
            else:
                cmd = ["ping", "-c", "1", "-W", "1", ip]
            rc = subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if rc == 0:
                live.add(ip)
        except Exception:
            pass
    return sorted(live, key=lambda x: tuple(int(p) for p in x.split(".")))


def ping_host(ip: str, samples: int = 3, timeout_ms: int = 500) -> Tuple[Optional[float], int]:
    times: List[float] = []
    for _ in range(samples):
        try:
            if os.name == "nt":
                cmd = ["ping", "-n", "1", "-w", str(timeout_ms), ip]
                timeout = max(1, timeout_ms // 1000 + 1)
            else:
                cmd = ["ping", "-c", "1", "-W", str(max(1, timeout_ms // 1000)), ip]
                timeout = max(1, timeout_ms // 1000 + 1)
            t0 = time.perf_counter()
            rc = subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout)
            if rc == 0:
                times.append((time.perf_counter() - t0) * 1000)
        except Exception:
            pass
    if not times:
        return None, 0
    return sum(times) / len(times), len(times)


def tcp_open(ip: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except Exception:
        return False


def http_probe(ip: str, port: int, https: bool, timeout: float = 0.7) -> Dict[str, Any]:
    headers: Dict[str, str] = {}
    body = ""
    try:
        if https:
            ctx = ssl._create_unverified_context()
            conn: http.client.HTTPConnection = http.client.HTTPSConnection(ip, port, timeout=timeout, context=ctx)
        else:
            conn = http.client.HTTPConnection(ip, port, timeout=timeout)
        conn.request("GET", "/", headers={"Connection": "close", "User-Agent": "NHA/1.0"})
        resp = conn.getresponse()
        headers = {k.lower(): v for k, v in resp.getheaders()}
        body = (resp.read(4096) or b"").decode("utf-8", errors="ignore")
        status = resp.status
    except Exception:
        status = None
    finally:
        try:
            conn.close()  # type: ignore[name-defined]
        except Exception:
            pass

    title_m = re.search(r"<title>(.*?)</title>", body, re.I | re.S)
    return {
        "port": port,
        "scheme": "https" if https else "http",
        "status": status,
        "server": headers.get("server", ""),
        "title": title_m.group(1).strip() if title_m else "",
    }


def _parse_percent(value: Any) -> Optional[int]:
    m = re.search(r"(\d+)", str(value or ""))
    if not m:
        return None
    return int(m.group(1))


def _netsh_wlan(args: List[str]) -> str:
    if os.name != "nt":
        return ""
    try:
        return _run(["netsh", "wlan"] + args, timeout=12)
    except Exception:
        return ""


def split_capture_sections(txt: str) -> Tuple[str, str]:
    current = txt
    visible = txt
    current_marker = "=== CURRENT CONNECTION ==="
    visible_marker = "=== VISIBLE BSSIDS ==="
    if current_marker in txt:
        current = txt.split(current_marker, 1)[1]
        if visible_marker in current:
            current = current.split(visible_marker, 1)[0]
    if visible_marker in txt:
        visible = txt.split(visible_marker, 1)[1]
    return current, visible


def wifi_interfaces(txt: Optional[str] = None) -> List[Dict[str, Any]]:
    txt = txt if txt is not None else _netsh_wlan(["show", "interfaces"])
    if not txt:
        return []

    key_map = {
        "name": "name",
        "description": "description",
        "state": "state",
        "ssid": "ssid",
        "bssid": "bssid",
        "ap bssid": "bssid",
        "radio type": "radio_type",
        "band": "band",
        "channel": "channel",
        "receive rate (mbps)": "rx_mbps",
        "transmit rate (mbps)": "tx_mbps",
        "signal": "signal_pct",
    }
    rows: List[Dict[str, Any]] = []
    current: Dict[str, Any] = {}
    for line in txt.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = re.sub(r"\s+", " ", key.strip().lower())
        value = value.strip()
        if key == "name" and current:
            rows.append(current)
            current = {}
        mapped = key_map.get(key)
        if mapped:
            current[mapped] = _parse_percent(value) if mapped == "signal_pct" else value
    if current:
        rows.append(current)

    for row in rows:
        if row.get("bssid"):
            row["bssid"] = normalize_mac(row["bssid"])
    return [row for row in rows if str(row.get("state", "")).lower() == "connected" or row.get("ssid")]


def wifi_bssid_survey(txt: Optional[str] = None) -> List[Dict[str, Any]]:
    txt = txt if txt is not None else _netsh_wlan(["show", "networks", "mode=bssid"])
    if not txt:
        return []

    records: List[Dict[str, Any]] = []
    ssid = ""
    current: Optional[Dict[str, Any]] = None
    for line in txt.splitlines():
        m_ssid = re.match(r"\s*SSID\s+\d+\s*:\s*(.*)$", line)
        if m_ssid:
            ssid = m_ssid.group(1).strip()
            current = None
            continue
        m_bssid = re.match(r"\s*BSSID\s+\d+\s*:\s*([0-9a-fA-F:\-]{17})", line)
        if m_bssid:
            current = {"ssid": ssid, "bssid": normalize_mac(m_bssid.group(1))}
            records.append(current)
            continue
        if current and ":" in line:
            key, value = line.split(":", 1)
            key = re.sub(r"\s+", " ", key.strip().lower())
            value = value.strip()
            if key == "signal":
                current["signal_pct"] = _parse_percent(value)
            elif key == "radio type":
                current["radio_type"] = value
            elif key == "channel":
                current["channel"] = value
    return records


def node_label(ip: str, node: Dict[str, Any]) -> str:
    name = node.get("name") or ""
    return f"{name} ({ip})" if name else ip


def node_for_bssid(bssid: str, nodes: Dict[str, Dict[str, Any]]) -> Optional[Tuple[str, Dict[str, Any]]]:
    bssid = normalize_mac(bssid)
    if not bssid:
        return None
    for ip, node in nodes.items():
        candidates = {normalize_mac(node.get("mac"))}
        candidates.update(normalize_mac(v) for v in node.get("bssids", []) or [])
        if bssid in candidates:
            return ip, node
    return None


def load_deco_nodes(cfg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    configured = known_nodes_from_config(cfg)
    return configured or DEFAULT_DECO_NODES


def node_statuses(nodes: Dict[str, Dict[str, Any]], arp: Dict[str, str]) -> List[Dict[str, Any]]:
    statuses: List[Dict[str, Any]] = []
    for ip, node in nodes.items():
        rtt, replies = ping_host(ip)
        ports = {str(port): tcp_open(ip, port) for port in (80, 443, 8080, 8443)}
        probes = []
        for port, https in ((80, False), (443, True)):
            if ports.get(str(port)):
                probes.append(http_probe(ip, port, https))
        statuses.append({
            "ip": ip,
            "name": node.get("name", ""),
            "mac": node.get("mac", ""),
            "arp_mac": arp.get(ip, ""),
            "reachable": replies > 0 or bool(arp.get(ip)),
            "ping_ms": round(rtt, 1) if rtt is not None else None,
            "ping_replies": replies,
            "open_ports": [int(port) for port, is_open in ports.items() if is_open],
            "http": probes,
        })
    return statuses


def api_attachment_summary(clients: List[Dict[str, Any]], nodes: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for client in clients:
        ap_mac = normalize_mac(client.get("ap_mac"))
        groups[ap_mac or "unknown"].append(client)

    attachments = []
    for ap_mac, items in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        matched = node_for_bssid(ap_mac, nodes) if ap_mac != "unknown" else None
        attachments.append({
            "ap_mac": ap_mac,
            "node_ip": matched[0] if matched else "",
            "node_name": matched[1].get("name", "") if matched else "",
            "client_count": len(items),
            "clients": [
                {
                    "ip": c.get("ip", ""),
                    "mac": c.get("mac", ""),
                    "hostname": c.get("hostname", ""),
                    "band": c.get("band", ""),
                    "rssi": c.get("rssi"),
                }
                for c in items
            ],
        })
    return {"client_count": len(clients), "attachments": attachments}


def roaming_findings(current: Optional[Dict[str, Any]], survey: List[Dict[str, Any]],
                     nodes: Dict[str, Dict[str, Any]]) -> List[str]:
    findings: List[str] = []
    if not current:
        findings.append("This machine is not reporting an active Wi-Fi interface via netsh.")
        return findings

    ssid = current.get("ssid") or ""
    current_bssid = normalize_mac(current.get("bssid"))
    current_signal = current.get("signal_pct")
    same_ssid = [row for row in survey if row.get("ssid") == ssid and row.get("signal_pct") is not None]
    same_ssid.sort(key=lambda row: int(row.get("signal_pct") or 0), reverse=True)

    if current_signal is not None and current_signal < 55:
        findings.append(f"Current laptop Wi-Fi signal is weak at {current_signal}% on BSSID {current_bssid}.")
    if len(same_ssid) < 2:
        findings.append(f"Only {len(same_ssid)} BSSID(s) for SSID '{ssid}' are visible from this laptop.")
        return findings

    strongest = same_ssid[0]
    strongest_bssid = normalize_mac(strongest.get("bssid"))
    strongest_signal = int(strongest.get("signal_pct") or 0)
    if current_signal is None:
        current_match = next((row for row in same_ssid if normalize_mac(row.get("bssid")) == current_bssid), None)
        current_signal = int(current_match.get("signal_pct") or 0) if current_match else None

    if current_bssid and strongest_bssid != current_bssid and current_signal is not None:
        delta = strongest_signal - int(current_signal)
        if delta >= 15:
            cur_node = node_for_bssid(current_bssid, nodes)
            strong_node = node_for_bssid(strongest_bssid, nodes)
            cur_label = node_label(cur_node[0], cur_node[1]) if cur_node else current_bssid
            strong_label = node_label(strong_node[0], strong_node[1]) if strong_node else strongest_bssid
            findings.append(
                f"Roaming concern: laptop is on {cur_label} at {current_signal}%, "
                f"but {strong_label} is visible at {strongest_signal}%."
            )
    return findings


def print_node_statuses(statuses: List[Dict[str, Any]]) -> None:
    print("Configured Deco nodes")
    print("-" * 60)
    for status in statuses:
        label = f"{status['name']} ({status['ip']})" if status.get("name") else status["ip"]
        ping = f"{status['ping_ms']}ms" if status.get("ping_ms") is not None else "no ping"
        arp = f", arp {status['arp_mac']}" if status.get("arp_mac") else ""
        ports = ",".join(str(p) for p in status.get("open_ports", [])) or "none"
        print(f"  {label:28s} {ping:10s} ports={ports}{arp}")
        for probe in status.get("http", []):
            title = probe.get("title") or probe.get("server") or ""
            print(f"    {probe['scheme']}:{probe['port']} status={probe['status']} {title}".rstrip())


def print_wifi(current: Optional[Dict[str, Any]], survey: List[Dict[str, Any]],
               nodes: Dict[str, Dict[str, Any]]) -> None:
    print()
    print("Laptop Wi-Fi association")
    print("-" * 60)
    if not current:
        print("  No connected Wi-Fi interface reported by Windows.")
        return

    bssid = normalize_mac(current.get("bssid"))
    matched = node_for_bssid(bssid, nodes)
    matched_text = f" ({node_label(matched[0], matched[1])})" if matched else ""
    print(f"  SSID:   {current.get('ssid', '')}")
    print(f"  BSSID:  {bssid}{matched_text}")
    print(f"  Signal: {current.get('signal_pct', '?')}%  Channel: {current.get('channel', '?')}  Radio: {current.get('radio_type', '?')}")

    same_ssid = [row for row in survey if row.get("ssid") == current.get("ssid")]
    same_ssid.sort(key=lambda row: int(row.get("signal_pct") or 0), reverse=True)
    if not same_ssid:
        return

    print()
    print(f"Visible BSSIDs for SSID '{current.get('ssid', '')}'")
    print("-" * 60)
    for row in same_ssid[:12]:
        rbssid = normalize_mac(row.get("bssid"))
        matched = node_for_bssid(rbssid, nodes)
        label = node_label(matched[0], matched[1]) if matched else rbssid
        marker = "*" if rbssid == bssid else " "
        print(f" {marker} {label:28s} {row.get('signal_pct', '?')}%  ch {row.get('channel', '?')}  {row.get('radio_type', '')}")


def print_api_summary(summary: Dict[str, Any]) -> None:
    print()
    print("Deco API client attachment")
    print("-" * 60)
    if summary["client_count"] == 0:
        print("  No clients returned by the local Deco API probes.")
        print("  The diagnostic will not infer whole-home client distribution from pings.")
        return

    print(f"  Clients returned: {summary['client_count']}")
    for group in summary["attachments"]:
        label = group["node_name"] or group["node_ip"] or group["ap_mac"]
        print(f"  {label:28s} {group['client_count']} client(s)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Deco mesh and Wi-Fi roaming diagnostics")
    parser.add_argument("--cidr", default="", help="Subnet (auto-detected if empty)")
    parser.add_argument("--json", action="store_true", help="Also print JSON report")
    parser.add_argument("--quick", action="store_true", help="Skip full LAN host discovery")
    parser.add_argument("--skip-api", action="store_true", help="Skip local Deco API probes")
    parser.add_argument("--capture-file", default="", help="Analyze saved netsh capture instead of local Wi-Fi")
    args = parser.parse_args()

    cfg = load_config()
    deco_cfg = ((cfg.get("integrations", {}) or {}).get("deco", {}) or {})
    gateway = _find_gateway()
    cidr = args.cidr or (gateway.rsplit(".", 1)[0] + ".0/24" if gateway else "192.168.1.0/24")
    nodes = load_deco_nodes(cfg)
    arp = _arp_table()

    print(f"Subnet: {cidr}  Gateway: {gateway or '(unknown)'}")
    live_hosts: List[str] = []
    if not args.quick:
        print("Discovering live hosts...")
        live_hosts = discover_live(cidr)
        print(f"  Found {len(live_hosts)} live host(s)")

    statuses = node_statuses(nodes, arp)
    print()
    print_node_statuses(statuses)

    capture_current = capture_visible = None
    if args.capture_file:
        capture_text = Path(args.capture_file).read_text(encoding="utf-8", errors="replace")
        capture_current, capture_visible = split_capture_sections(capture_text)

    interfaces = wifi_interfaces(capture_current)
    current_wifi = interfaces[0] if interfaces else None
    survey = wifi_bssid_survey(capture_visible)
    print_wifi(current_wifi, survey, nodes)

    clients: List[Dict[str, Any]] = []
    if not args.skip_api and deco_cfg.get("enabled", True):
        try:
            clients = fetch_clients(deco_cfg)
        except Exception as exc:
            print()
            print(f"Deco API probe failed: {exc}")
    api_summary = api_attachment_summary(clients, nodes)
    print_api_summary(api_summary)

    findings = roaming_findings(current_wifi, survey, nodes)
    if not clients:
        unmatched = [
            row.get("bssid")
            for row in survey
            if row.get("ssid") == (current_wifi or {}).get("ssid")
            and row.get("bssid")
            and node_for_bssid(str(row.get("bssid")), nodes) is None
        ]
        if unmatched:
            findings.append(
                "Deco local API did not return attachment data; add unmatched BSSIDs in config "
                f"to map visible radios to node names: {', '.join(unmatched[:6])}."
            )
        else:
            findings.append("Deco local API did not return whole-home client attachment data.")
    if not args.capture_file and any(not status.get("reachable") for status in statuses):
        down = [status["name"] or status["ip"] for status in statuses if not status.get("reachable")]
        findings.append(f"Configured Deco node(s) not reachable by ARP or ping: {', '.join(down)}.")

    print()
    print("Findings")
    print("-" * 60)
    if findings:
        for item in findings:
            print(f"  - {item}")
    else:
        print("  No local roaming imbalance was detected from this laptop's current position.")

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "subnet": cidr,
        "gateway": gateway,
        "live_hosts": len(live_hosts) if live_hosts else None,
        "nodes": statuses,
        "wifi": {
            "current": current_wifi,
            "visible_bssids": survey,
        },
        "deco_api": api_summary,
        "findings": findings,
    }
    out_path = Path("./mesh_topology_report.json")
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print()
    print(f"Report saved: {out_path.resolve()}")
    if args.json:
        print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
