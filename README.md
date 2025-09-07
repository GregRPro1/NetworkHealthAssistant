# Network Health Assistant — Full Package (Core + GUI)
This package contains:
- **Core scanner/analyzer** (no external deps): ARP scan, optional nmap enrichment, OUI/vendor lookup, heuristics, risk scoring, baseline/history, AI-ready payloads, JSON/Markdown reports.
- **Professional dark PyQt6 GUI**: Devices, Identify (AI stub), Tasks, Threats/AI tabs + traffic-light status.

## Quick Start (Windows PowerShell)
```powershell
# 1) Create venv & install
python -m venv .venv
. .venv/Scripts/Activate.ps1
pip install -r requirements.txt

# 2) Build the PDF and run smoke tests
python tools/build_userguide.py
python tests/smoke_tests.py

# 3) Start the API server (optional for iOS)
python -m src.server.api

# 4) Launch the GUI
python gui_main.py

```

Outputs go to `./data/`.

## Folders
- `src/nha` — core library & CLI
- top-level GUI files — `gui_main.py`, `styles.py`, `tabs_*.py`, `nha_bridge.py`

## AI Integration
- `data/ai_payload.json` is produced by `analyze` (contains prompt + inventory).
- Replace `src/nha/ai_client.py` and GUI stubs in `gui_main.py` with your Persistent Assistant client.


## Persistent Assistant integration
Edit `config.yaml` to point to your PA repo and entrypoint:

```yaml
ai:
  persistent_assistant_path: "C:/_Repos/PersistentAssistant"
  entrypoint: "pa.ai_client:analyze_inventory"
```

The GUI will continue to run even if PA is missing; it will use the local stub instead.


## Network health checks
Edit `config.yaml` to enable WAN/LAN tests and printers:

```yaml
health:
  internet_hosts: ["1.1.1.1", "8.8.8.8"]
  lan_targets: ["192.168.1.1"]
  printers:
    - { name: "Office Printer", ip: "192.168.1.50" }
  speedtest:
    enabled: true
    interval_min: 120
    binary: "speedtest"        # or "speedtest-cli"
  iperf3:
    enabled: false
    server: "192.168.1.2"
```
- **WAN**: averages ping across `internet_hosts`; optional `speedtest` shows Mbps.
- **LAN**: optional `iperf3` if you run a server on your LAN.
- **Printers**: quick online check via common ports (9100/631).
Status bar shows **WAN latency / speed** and **printer online/offline** summary.


## Settings tab
- Edit `config.yaml` directly inside the app.
- **Detect**: guesses default gateway, common internet hosts, finds printers by probing ports 9100/631, and guesses `speedtest` binary.
- **Export IoT for Home Assistant**: writes `data/home_assistant_iot.json` and `.yaml` listing IoT/camera devices (by MAC/IP/vendor/category/hostname). You can import this into Home Assistant via a custom integration or scripts.

## Should we use Home Assistant or expand this app?
- **Recommendation**: Use **Home Assistant** for **automation** and UI for device control, and keep **this app focused on network health, security posture, and AI advice**. Integrate the two:
  - Export IoT inventory (this app → HA).
  - Optionally send events (new device / high-risk) to HA via webhook or MQTT for notifications and automations.
- This division gives you best-in-class automation (HA) and a dedicated **security brain** (this app) without reinventing the wheel.

### Mobile app
- Start with a **thin companion** that consumes the JSON from `./data/` (or an HTTP endpoint we can expose later), showing posture, tasks, and alerts. For cross‑platform, consider **Flutter** or **React Native**.


## Built-in API (FastAPI)
Run:
```bash
python -m src.server.api
```
Defaults to http://0.0.0.0:8765 (LAN). Configure bearer **token** in `config.yaml` under `api.token`.

### Endpoints
- `GET /api/v1/report` — returns the latest report (JSON)
- `GET /api/v1/health` — WAN latency + optional speedtest/iperf3
- `POST /api/v1/scan` — runs scan + analyze
- `POST /api/v1/analyze` — re-runs analyze
- `GET /api/v1/threats` — placeholder (wire to PA)

**Note**: If `api.token` is set, include header `Authorization: Bearer <token>`.
