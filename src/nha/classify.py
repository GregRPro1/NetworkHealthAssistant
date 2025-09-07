from .oui import lookup_vendor

def classify_device(hostname: str, vendor: str, ports: list[str]) -> str:
    h = (hostname or "").lower()
    v = (vendor or "").lower()
    ports = ports or []
    if "iphone" in h or "ipad" in h or ("apple" in v and "62078/tcp" in ports):
        return "phone/tablet"
    if "android" in h or "samsung" in v:
        return "phone/tablet"
    if "raspberry" in h or "raspberry pi" in v:
        return "embedded/linux"
    if any(x in v for x in ["asus", "intel", "microsoft", "lenovo", "dell"]):
        return "pc/laptop"
    if any(x in h for x in ["roku","chromecast","shield","tv"]) or any(x in v for x in ["lg","google"]):
        return "tv/streaming"
    if any(x in v for x in ["tplink", "huawei", "xiaomi", "espressif"]):
        return "iot"
    if any(p.startswith("554/") for p in ports):
        return "camera/iot"
    if any(p.startswith(x) for x in ["80/","443/"]) and vendor == "Unknown":
        return "unknown/web"
    return "unknown"

def enrich_identity(dev: dict) -> dict:
    vendor = lookup_vendor(dev.get("mac",""))
    category = classify_device(dev.get("hostname",""), vendor, dev.get("ports",[]))
    return {**dev, "vendor": vendor, "category": category}
