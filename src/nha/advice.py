def priority_actions(analyzed):
    actions = []
    for d in analyzed:
        mac = d.get("mac"); cat = d.get("category","unknown")
        vend = d.get("vendor","Unknown"); score = d.get("risk_score",0)
        ports = d.get("ports", []); ip = d.get("ip","")
        if score >= 6:
            if "camera" in cat or any(p.startswith("554/") for p in ports):
                actions.append({"priority":1,"title":f"Isolate potential camera at {ip} ({vend})",
                                "detail":"Move to IoT VLAN/Guest SSID; block LAN; allow WAN only if needed. Update creds/firmware.",
                                "targets":[mac]})
            else:
                actions.append({"priority":2,"title":f"Investigate high-risk device at {ip} ({vend}, {cat})",
                                "detail":"Confirm identity; restrict services; move to IoT VLAN if non-PC.",
                                "targets":[mac]})
        elif score >= 3:
            actions.append({"priority":3,"title":f"Review medium-risk device at {ip} ({vend}, {cat})",
                            "detail":"Label device; ensure strong Wi‑Fi; consider isolation if IoT; disable UPnP/NAT‑PMP.",
                            "targets":[mac]})
        else:
            actions.append({"priority":4,"title":f"Low-risk: label and baseline {ip} ({vend}, {cat})",
                            "detail":"Record friendly name; keep firmware updated.", "targets":[mac]})
    actions.sort(key=lambda a: (a["priority"],))
    return actions
