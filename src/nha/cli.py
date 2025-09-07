import socket
from .config import load_config
from .scanner import run_scan
from .storage import paths, load_current, save_current, load_baseline, save_baseline
from .analyze import analyze
from .report import make_report
from .ai_client import analyze_with_ai
from .utils import write_json
from .logger import get_logger

def _resolve_hostnames(devs):
    for d in devs:
        ip = d.get("ip")
        try:
            d["hostname"] = socket.gethostbyaddr(ip)[0]
        except Exception:
            d["hostname"] = None
    return devs

def scan():
    log = get_logger()
    cfg = load_config()
    p = paths(cfg["storage"]["root"])
    devs = run_scan()
    devs = _resolve_hostnames(devs)
    save_current(cfg["storage"]["root"], devs)
    log.info(f"scan: {len(devs)} devices → {p['current']}")

def analyze_cmd():
    log = get_logger()
    cfg = load_config()
    p = paths(cfg["storage"]["root"])
    current = load_current(cfg["storage"]["root"])["devices"]
    baseline = load_baseline(cfg["storage"]["root"])["devices"]
    analyzed, summary = analyze(current, baseline)
    inventory = {"devices": analyzed, "summary": summary}
    ai_payload = analyze_with_ai(inventory)
    write_json(p["ai_payload"], {"inventory": inventory, **ai_payload})
    save_baseline(cfg["storage"]["root"], analyzed)
    make_report(analyzed, summary, p)
    log.info(f"analyze: total={summary['total']}, new={summary['new_devices']} → {p['report_json']}")

def report():
    analyze_cmd()

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m nha.cli [scan|analyze|report]"); raise SystemExit(1)
    cmd = sys.argv[1].lower()
    if cmd == "scan": scan()
    elif cmd == "analyze": analyze_cmd()
    elif cmd == "report": report()
    else:
        print("Unknown command:", cmd); raise SystemExit(2)
