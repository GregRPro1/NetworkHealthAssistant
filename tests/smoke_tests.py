"""
Basic smoke tests:
- Load config
- Run scan + analyze via library
- Build report.json
- Start FastAPI app in-process and hit /api/v1/report via TestClient
Logs written to data/app.log
"""
import os, json
from src.nha.config import load_config
from src.nha.cli import scan as scan_cli, analyze_cmd as analyze_cli
from src.server.api import app
from fastapi.testclient import TestClient
from src.nha.logger import get_logger

def main():
    log = get_logger("smoke")
    cfg = load_config()
    log.info("Loaded config: %s", cfg)
    scan_cli()
    analyze_cli()
    assert os.path.exists("./data/report.json"), "report.json missing after analyze"
    with open("./data/report.json","r",encoding="utf-8") as f:
        report = json.load(f)
    log.info("Report summary: %s", report.get("summary"))
    # API test
    client = TestClient(app)
    headers = {}
    token = cfg.get("api", {}).get("token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = client.get("/api/v1/report", headers=headers)
    assert r.status_code == 200, "API /report failed"
    log.info("/api/v1/report OK, %d bytes", len(r.content))
    print("SMOKE TESTS PASSED")

if __name__ == "__main__":
    main()
