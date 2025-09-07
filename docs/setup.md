# Setup

## Requirements
- Python 3.11+
- Windows/macOS/Linux
- Optional tools: `nmap`, Ookla `speedtest` or `speedtest-cli`, `iperf3`

## Install
```bash
python -m venv .venv
# Windows
. .venv/Scripts/Activate.ps1
# macOS/Linux
# source .venv/bin/activate
pip install -r requirements.txt
```

## Run GUI
```bash
python gui_main.py
```

## API Server (FastAPI)
```bash
python -m src.server.api
```
Edit `config.yaml` → set `api.token` for Bearer auth.
