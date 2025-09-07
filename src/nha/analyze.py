from collections import defaultdict
from .logger import get_logger
from .classify import enrich_identity

RISK_RULES = {
    "unknown_vendor": 3, "unknown_category": 2,
    "camera_ports": 4, "many_open_ports": 2, "new_device": 3,
}

def compute_risk(dev, is_new=False):
    score, reasons = 0, []
    if dev.get("vendor") == "Unknown":
        score += RISK_RULES["unknown_vendor"]; reasons.append("unknown_vendor")
    if dev.get("category","unknown").startswith("unknown"):
        score += RISK_RULES["unknown_category"]; reasons.append("unknown_category")
    ports = dev.get("ports", [])
    if any(p.startswith("554/") for p in ports):
        score += RISK_RULES["camera_ports"]; reasons.append("camera_ports")
    if len(ports) >= 5:
        score += RISK_RULES["many_open_ports"]; reasons.append("many_open_ports")
    if is_new:
        score += RISK_RULES["new_device"]; reasons.append("new_device")
    return score, reasons

def analyze(current_devices, baseline_devices):
    log = get_logger()
    by_mac = {d.get("mac"): d for d in baseline_devices if d.get("mac")}
    log.info(f'analyze: current={len(current_devices)} baseline={len(baseline_devices)}'); analyzed, new_count = [], 0
    for d in current_devices:
        e = enrich_identity(d)
        is_new = e.get("mac") not in by_mac
        if is_new: new_count += 1
        score, reasons = compute_risk(e, is_new=is_new)
        e["risk_score"] = score; e["risk_reasons"] = reasons
        analyzed.append(e)

    analyzed.sort(key=lambda x: x.get("risk_score", 0), reverse=True)
    summary = {"total": len(analyzed), "new_devices": new_count, "by_category": defaultdict(int), "risk_buckets": {"high":0,"medium":0,"low":0}}
    for a in analyzed:
        summary["by_category"][a.get("category","unknown")] += 1
        if a["risk_score"] >= 6: summary["risk_buckets"]["high"] += 1
        elif a["risk_score"] >= 3: summary["risk_buckets"]["medium"] += 1
        else: summary["risk_buckets"]["low"] += 1
    summary["by_category"] = dict(summary["by_category"])
    return analyzed, summary
