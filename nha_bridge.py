import json, os, subprocess, sys, socket
from pathlib import Path

def _try_import():
    try:
        from src.nha.storage import paths, load_current, load_baseline
        from src.nha.analyze import analyze
        from src.nha.report import make_report
        from src.nha.cli import scan as nha_scan
        return {"ok": True, "mode": "lib", "scan": nha_scan, "analyze": analyze,
                "load_current": load_current, "load_baseline": load_baseline,
                "paths": paths, "make_report": make_report}
    except Exception as e:
        return {"ok": False, "err": str(e)}

LIB = _try_import()

def ensure_data_root():
    root = "./data"
    os.makedirs(root, exist_ok=True)
    return root

def run_scan():
    ensure_data_root()
    if LIB["ok"] and LIB["mode"] == "lib":
        LIB["scan"](); return True, "scan via lib"
    try:
        subprocess.check_call([sys.executable, "-m", "nha.cli", "scan"])
        return True, "scan via CLI"
    except Exception as e:
        return False, f"scan failed: {e}"

def run_analyze():
    ensure_data_root()
    if LIB["ok"] and LIB["mode"] == "lib":
        p = LIB["paths"]("./data")
        current = LIB["load_current"]("./data")["devices"]
        baseline = LIB["load_baseline"]("./data")["devices"]
        analyzed, summary = LIB["analyze"](current, baseline)
        LIB["make_report"](analyzed, summary, p)
        return True, {"analyzed": analyzed, "summary": summary, "paths": p}
    try:
        subprocess.check_call([sys.executable, "-m", "nha.cli", "report"])
        with open("./data/report.json","r",encoding="utf-8") as f:
            d = json.load(f)
        return True, {"analyzed": d.get("devices",[]), "summary": d.get("summary",{}), "paths": {"report_json":"./data/report.json"}}
    except Exception as e:
        return False, f"analyze/report failed: {e}"

def load_report_json():
    try:
        with open("./data/report.json","r",encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}
