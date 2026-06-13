# src/nha/classify.py
from __future__ import annotations
from typing import List, Dict, Any
import socket

# ---- reverse DNS -------------------------------------------------------------

def _best_effort_rdns(ip: str, timeout: float = 0.6) -> str:
    if not ip:
        return ""
    prev = None
    try:
        prev = socket.getdefaulttimeout()
        socket.setdefaulttimeout(timeout)
        name = socket.gethostbyaddr(ip)[0]
        return name or ""
    except Exception:
        return ""
    finally:
        try:
            socket.setdefaulttimeout(prev)
        except Exception:
            pass

# ---- helpers ----------------------------------------------------------------

def _has(ports: List[str] | None, prefix: str) -> bool:
    return any(str(p).startswith(prefix) for p in (ports or []))

def _contains_any(s: str, words: tuple[str, ...]) -> bool:
    s = s.lower()
    return any(w in s for w in words)

# ---- primary classifier ------------------------------------------------------

def classify_device(hostname: str, vendor: str, ports: List[str] | None) -> str:
    """
    Heuristic device categorization by hostname, vendor and open ports.
    """
    hn = (hostname or "").lower()
    ven = vendor or "Unknown"
    ven_l = ven.lower()
    ports = ports or []

    # High-confidence by service
    if _has(ports, "9100/") or _has(ports, "631/") or "printer" in hn or _contains_any(ven_l, ("hp inc","hewlett","brother","canon","epson","xerox","kyocera","ricoh")):
        return "Printer"
    if _has(ports, "554/") or "rtsp" in hn or "cam" in hn or "camera" in hn or _contains_any(ven_l, ("hikvision","ezviz","reolink","arlo","dahua")):
        return "Camera/IoT"

    # Windows PC clues
    if any(_has(ports, p) for p in ("135/","139/","445/","3389/")):
        return "PC/Laptop (Windows)"

    # SSH likely infra/server
    if _has(ports, "22/"):
        return "Server/Infra"

    # Router/AP vendors
    if _contains_any(ven_l, ("tp-link","tplink","netgear","asus","belkin","ubiquiti","mikrotik","tp link")):
        return "Router/AP"

    # Console / TV
    if _contains_any(ven_l, ("sony interactive","playstation","nintendo","microsoft")) or _contains_any(hn, ("ps4","ps5","xbox","switch")):
        return "Game Console / TV"
    if _contains_any(ven_l, ("lg","hisense","tcl","philips tv","samsung electronics")) or "tv" in hn:
        return "Smart TV"

    # Phone / tablet
    if _contains_any(ven_l, ("apple","samsung","google","xiaomi","huawei","oneplus","oppo")) or _contains_any(hn, ("iphone","ipad","android","pixel")):
        return "Phone/Tablet"

    # PC vendors
    if _contains_any(ven_l, ("dell","hp","hewlett-packard","lenovo","acer","msi","asus","gigabyte")):
        return "PC/Laptop"

    # Generic IoT
    if (_has(ports, "80/") or _has(ports, "443/")) and ven == "Unknown":
        return "IoT (web-managed)"

    return "Unknown"

def likely_hint(hostname: str, vendor: str, ports: List[str] | None) -> str | None:
    """
    Produce a low-confidence hint string for Unknown categories.
    """
    hn = (hostname or "").lower()
    ven_l = (vendor or "Unknown").lower()
    ports = ports or []
    if hn.endswith(".1") or hn.endswith("-gateway") or "router" in hn:
        return "Likely your router/gateway"
    if _contains_any(ven_l, ("belkin","wemo")):
        return "Likely Belkin/Wemo smart plug"
    if _contains_any(ven_l, ("tplink","tp-link")) and (_has(ports,"80/") or _has(ports,"443/")):
        return "TP-Link device (router/AP/switch)"
    if _has(ports, "53/"):
        return "DNS-capable device"
    if _has(ports, "1900/"):
        return "UPnP/SSDP responder"
    if _has(ports, "5353/"):
        return "mDNS/Bonjour responder (Apple/IoT)"
    if _has(ports, "23/"):
        return "Telnet-enabled device (legacy/unsafe)"
    return None

# ---- public API --------------------------------------------------------------

def enrich_identity(dev: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns a copy with:
      - hostname (best-effort rDNS if missing)
      - category (heuristic)
      - issues list appended with low-confidence 'hint' if still Unknown
    """
    d = dict(dev)
    if not d.get("hostname"):
        d["hostname"] = _best_effort_rdns(d.get("ip",""))
    vendor = d.get("vendor", "Unknown")
    ports  = d.get("ports", []) or []
    d["category"] = classify_device(d.get("hostname",""), vendor, ports)

    if d["category"] == "Unknown":
        h = likely_hint(d.get("hostname",""), vendor, ports)
        if h:
            issues = list(d.get("issues", []))
            issues.append(h)
            d["issues"] = issues
    return d
