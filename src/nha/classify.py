# src/nha/classify.py
from typing import List, Dict

def classify_device(hostname: str, vendor: str, ports: List[str]) -> str:
    """
    Very light heuristic category classifier.
    ports entries are strings like "80/tcp", "554/tcp", "9100/tcp".
    """
    hn = (hostname or "").lower()
    ven = (vendor or "Unknown")
    ports = ports or []

    has = lambda pref: any(str(port).startswith(pref) for port in ports)

    # Cameras tend to expose RTSP
    if has("554/") or "cam" in hn or "camera" in hn:
        return "camera/iot"

    # Printers: 9100 RAW / 631 IPP
    if has("9100/") or has("631/") or "printer" in hn:
        return "printer/iot"

    # Phones/tablets
    if any(k in hn for k in ("iphone", "ipad", "android", "pixel")) or ven in ("Apple", "Samsung", "Google"):
        return "phone/tablet"

    # Desktops/laptops
    if any(k in hn for k in ("pc", "laptop", "desktop", "workstation")) or ven in ("ASUSTek", "Dell", "HP", "Lenovo", "Acer", "MSI"):
        return "pc/laptop"

    # Generic webby device with unknown vendor → likely IoT
    if (has("80/") or has("443/")) and ven == "Unknown":
        return "iot"

    return "unknown"

def enrich_identity(dev: Dict) -> Dict:
    d = dict(dev)
    vendor = d.get("vendor", "Unknown")
    d["category"] = classify_device(d.get("hostname", ""), vendor, d.get("ports", []) or [])
    return d
