# src/nha/ai_client.py
import json

PROMPT_TEMPLATE = """You are the Network Health Assistant.
You will receive a JSON inventory of devices discovered on a home LAN and produce:
- A short security summary (traffic-light style: High/Medium/Low).
- Prioritized actions to improve posture (isolation/VLAN, firmware updates, disable UPnP/WPS, rename/label, etc.).
- Identification hints for unknown devices and safe experiments (block, power-cycle, move SSID).
- Notes suitable for a non-expert user.

Inventory (JSON):
{inventory}

Guidelines:
- Be concise and specific. Prefer clear, numbered steps.
- For cameras/IoT with unknown vendors or open ports (e.g. 23/tcp, 554/tcp), recommend isolation and least-privilege Internet-only.
- If nothing is found, return an empty/low-risk summary and generic hardening steps (router posture, guest SSID for IoT, strong Wi-Fi keys).
"""

def build_prompt(inventory: dict) -> str:
    inv_json = json.dumps(inventory, indent=2)
    # Only one placeholder {inventory}; no other braces in PROMPT_TEMPLATE.
    return PROMPT_TEMPLATE.format(inventory=inv_json)

def analyze_with_ai(inventory: dict) -> dict:
    """
    Local stub: returns a structured payload that the app can render.
    Replace with your real AI call if desired (see ai_bridge.py).
    """
    prompt = build_prompt(inventory)
    # Minimal heuristic summary when running offline
    devices = inventory.get("devices", [])
    total = len(devices)
    high = sum(1 for d in devices if d.get("risk_score", 0) >= 6)
    med  = sum(1 for d in devices if 3 <= d.get("risk_score", 0) <= 5)

    if total == 0:
        ai_summary = "No devices detected in the latest scan. Posture appears low risk; run a scan after ensuring the adapter/permissions are correct."
        ai_suggestions = [
            "Verify network adapter and permissions (run as admin if required).",
            "Ensure ARP scan is permitted on this network; try again after activity.",
            "Harden router: disable WPS/UPnP, enforce WPA2/WPA3, use strong Wi-Fi keys."
        ]
    else:
        posture = "High" if high else ("Medium" if med else "Low")
        ai_summary = f"Detected {total} devices. Posture: {posture} risk (High={high}, Medium={med})."
        ai_suggestions = [
            "Label unknown devices (owner/room) and group IoT on an isolated SSID/VLAN.",
            "Update router and device firmware; disable unused services (e.g., UPnP).",
            "Restrict inbound access; for cameras/IoT, prefer Internet-only egress if possible."
        ]

    return {
        "prompt": prompt,
        "ai_summary": ai_summary,
        "ai_suggestions": ai_suggestions
    }
