OUI_MAP = {
    "D85D4C": "Apple, Inc.", "F0D1A9": "Samsung Electronics",
    "BC305B": "Amazon Technologies Inc.", "B827EB": "Raspberry Pi Foundation",
    "246F28": "Espressif Inc.", "F4F5E8": "LG Electronics",
    "001A11": "ASUSTek COMPUTER INC.", "5866BA": "HUAWEI TECHNOLOGIES CO.,LTD",
    "C83A35": "Xiaomi Communications Co Ltd", "AC9CE4": "Xiaomi Communications Co Ltd",
    "F4F5DB": "TP-LINK TECHNOLOGIES CO.,LTD.", "F8D111": "Google LLC",
}

def lookup_vendor(mac: str) -> str:
    mac = mac.upper().replace(":", "").replace("-", "")
    if len(mac) < 6:
        return "Unknown"
    return OUI_MAP.get(mac[:6], "Unknown")
