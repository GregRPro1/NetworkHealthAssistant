# src/nha/analyze.py
from __future__ import annotations
from typing import Dict, List, Tuple, Any
import ipaddress
from .classify import enrich_identity

def _normalize_devices(seq: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not seq:
        return out
    if isinstance(seq, dict):
        if "devices" in seq and isinstance(seq["devices"], list):
            return _normalize_devices(seq["devices"])
        return [seq]
    if not isinstance(seq, list):
        return out
    for item in seq:
        if isinstance(item, dict):
            out.append(item)
        elif isinstance(item, str):
            out.append({"ip": item})
    return out

def _is_multicast_or_broadcast(ip: str) -> bool:
    try:
        ipobj = ipaddress.ip_address(ip)
        return ipobj.is_multicast or ip.endswith(".255")
    except Exception:
        return False

def _score_device(d: Dict[str, Any]) -> Tuple[int, List[str]]:
    issues: List[str] = []
    ports  = [str(p) for p in (d.get("ports") or [])]
    vendor = d.get("vendor", "Unknown")
    hostname = d.get("hostname","")
    ip = d.get("ip","")

    if _is_multicast_or_broadcast(ip):
        return 1, ["System/multicast/broadcast address"]

    risk = 1

    # High
    if any(p.startswith("23/") for p in ports):
        risk = max(risk, 8); issues.append("Telnet (23/tcp) open")
    if any(p.startswith("3389/") for p in ports):
        risk = max(risk, 8); issues.append("RDP (3389/tcp) open")

    # Medium
    if any(p.startswith("445/") for p in ports):
        risk = max(risk, 5); issues.append("SMB (445/tcp) open")
    if any(p.startswith("554/") for p in ports):
        risk = max(risk, 5); issues.append("RTSP (554/tcp) open")
    if any(p.startswith("9100/") or p.startswith("631/") for p in ports):
        risk = max(risk, 5); issues.append("Printer service (9100/631) open")

    # Web-only + Unknown vendor => suspicious IoT
    if (any(p.startswith("80/") or p.startswith("443/") for p in ports)
        and vendor == "Unknown" and risk < 5):
        risk = max(risk, 4); issues.append("Unknown vendor with web port(s)")

    if vendor == "Unknown":
        risk = max(risk, risk + 1); issues.append("Unknown vendor")
    if not hostname:
        risk = max(risk, risk + 1); issues.append("No hostname")

    risk = max(1, min(risk, 10))
    return risk, issues

def analyze(current: Dict[str, Any], baseline: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    current_devices  = _normalize_devices(current.get("devices"))
    baseline_devices = _normalize_devices(baseline.get("devices"))

    known_keys = set()
    for b in baseline_devices:
        key = (b.get("mac") or b.get("ip"))
        if key:
            known_keys.add(key)

    analyzed: List[Dict[str, Any]] = []
    rbuckets = {"high": 0, "medium": 0, "low": 0}
    new_count = 0

    for d in current_devices:
        # identity enrichment (hostname + category + hints)
        dd = enrich_identity(d)

        # risk + reasons
        risk, issues = _score_device(dd)
        dd["risk_score"] = risk
        if issues:
            dd["issues"] = list(set(issues + dd.get("issues", [])))  # merge & dedupe

        if risk >= 7:
            rbuckets["high"] += 1
        elif risk >= 4:
            rbuckets["medium"] += 1
        else:
            rbuckets["low"] += 1

        key = (dd.get("mac") or dd.get("ip"))
        if key and key not in known_keys:
            new_count += 1

        analyzed.append(dd)

    summary = {
        "total": len(analyzed),
        "new_devices": new_count,
        "risk_buckets": rbuckets,
    }
    return analyzed, summary
