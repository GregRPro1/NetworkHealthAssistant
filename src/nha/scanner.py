import platform, re
from .logger import get_logger
from .utils import run_cmd_get_stdout, is_tool_on_path, now_iso

ARP_LINE_RE = re.compile(r"(?P<ip>\d+\.\d+\.\d+\.\d+)\s+[-\w]+\s+(?P<mac>[0-9a-fA-F:-]{17})", re.IGNORECASE)
UNIX_ARP_RE = re.compile(r"\((?P<ip>\d+\.\d+\.\d+\.\d+)\)\s+at\s+(?P<mac>[0-9a-fA-F:]{17})", re.IGNORECASE)

def scan_arp_table():
    sys = platform.system().lower()
    out = run_cmd_get_stdout(["arp", "-a"], timeout=10)
    devices = []
    if not out:
        return devices
    if "windows" in sys:
        for line in out.splitlines():
            m = ARP_LINE_RE.search(line)
            if m:
                devices.append({"ip": m.group("ip"), "mac": m.group("mac").lower(), "source": "arp"})
    else:
        for line in out.splitlines():
            m = UNIX_ARP_RE.search(line)
            if m:
                devices.append({"ip": m.group("ip"), "mac": m.group("mac").lower(), "source": "arp"})
    return devices

def enrich_with_nmap(ip_list):
    if not is_tool_on_path("nmap") or not ip_list:
        return {}
    results = {}
    cmd = ["nmap", "-T4", "-Pn", "-F"] + ip_list
    out = run_cmd_get_stdout(cmd, timeout=60)
    current_ip = None
    for line in out.splitlines():
        if "Nmap scan report for" in line:
            parts = line.strip().split()
            current_ip = parts[-1].strip("()")
            results[current_ip] = {"ports": []}
        elif "/tcp" in line and current_ip:
            try:
                port = line.strip().split()[0]
                results[current_ip]["ports"].append(port)
            except Exception:
                pass
    return results

def run_scan():
    log = get_logger()
    log.info('starting ARP scan'); base = scan_arp_table()
    log.info('optional nmap enrichment'); nmap_data = enrich_with_nmap([d["ip"] for d in base])
    timestamp = now_iso()
    for d in base:
        d["ports"] = nmap_data.get(d["ip"], {}).get("ports", [])
        d["seen_at"] = timestamp
    return base
