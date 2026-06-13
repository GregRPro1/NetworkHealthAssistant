# nha_bridge.py
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from src.nha.scanner import run_scan as core_run_scan
from src.nha.analyze import analyze as core_analyze
from src.nha.logger import get_logger

log = get_logger("nha")

DATA_DIR = Path("./data")

def _read_json(p: Path) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

def load_report_json() -> Dict[str, Any]:
    """
    Always return a dict with at least:
      {"summary": {...}, "devices": [], "actions": []}
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    p = DATA_DIR / "report.json"
    rep = _read_json(p) or {}
    if isinstance(rep, list):
        # legacy format, normalize
        rep = {"devices": rep}
    rep.setdefault("summary", {"total": 0, "new_devices": 0, "risk_buckets": {"high": 0, "medium": 0, "low": 0}})
    rep.setdefault("devices", [])
    rep.setdefault("actions", [])
    return rep

def load_current(data_dir: str | Path = DATA_DIR) -> Dict[str, Any]:
    """
    Return {"devices": [...]}. If file is a list, wrap it.
    """
    p = Path(data_dir) / "current_scan.json"
    cur = _read_json(p)
    if cur is None:
        return {"devices": []}
    if isinstance(cur, list):
        return {"devices": cur}
    if isinstance(cur, dict):
        # accept both {"devices":[...]} and raw device dict maps
        return {"devices": cur.get("devices", []) if "devices" in cur else []}
    return {"devices": []}

def load_baseline(data_dir: str | Path = DATA_DIR) -> Dict[str, Any]:
    """
    Return {"devices": [...]}. Missing file -> empty list.
    """
    p = Path(data_dir) / "baseline.json"
    base = _read_json(p)
    if base is None:
        return {"devices": []}
    if isinstance(base, list):
        return {"devices": base}
    if isinstance(base, dict):
        return {"devices": base.get("devices", []) if "devices" in base else []}
    return {"devices": []}

def save_report(report: Dict[str, Any], data_dir: str | Path = DATA_DIR) -> Path:
    p = Path(data_dir) / "report.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return p

def run_scan() -> List[Dict[str, Any]]:
    """
    Kick a scan via core scanner; returns device list.
    """
    devs = core_run_scan() or []
    if not isinstance(devs, list):
        log.warning("scanner returned non-list, normalizing")
        devs = []
    return devs

def run_analyze() -> Tuple[bool, Path]:
    """
    Load current + baseline, run analyzer, write report.json.
    Returns (ok, report_path).
    """
    cur = load_current(DATA_DIR)["devices"]
    base = load_baseline(DATA_DIR)["devices"]
    analyzed, summary = core_analyze({"devices": cur}, {"devices": base})
    report = {
        "summary": summary or {"total": len(analyzed), "new_devices": 0, "risk_buckets": {"high": 0, "medium": 0, "low": 0}},
        "devices": analyzed,
        "actions": []  # your analyzer may fill this later
    }
    path = save_report(report, DATA_DIR)
    log.info("analyze: total=%d, new=%d → %s", report["summary"].get("total", 0), report["summary"].get("new_devices", 0), path)
    return True, path
