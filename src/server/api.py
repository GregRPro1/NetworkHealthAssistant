from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os, json, time
from src.nha.config import load_config
from src.nha.storage import paths
from src.nha.net_health import ping_ms, speedtest, iperf3_test
from src.nha.cli import scan as scan_cli, analyze_cmd as analyze_cli
from src.nha.logger import get_logger

def get_token_dep():
    cfg = load_config()
    token = (cfg.get("api",{})).get("token", None)
    def dep(request: Request):
        if not token:
            return  # no token configured -> open
        auth = request.headers.get("authorization","")
        if not auth.lower().startswith("bearer "):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
        given = auth.split(" ",1)[1].strip()
        if given != token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return dep

log = get_logger('api')
app = FastAPI(title="Network Health Assistant API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False
)

@app.get("/api/v1/report")
def get_report(dep: None = Depends(get_token_dep())):
    log.info('GET /api/v1/report')
    p = paths("./data")
    try:
        with open(p["report_json"], "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"summary": {"total":0,"new_devices":0,"by_category":{},"risk_buckets":{"high":0,"medium":0,"low":0}}, "actions": [], "devices": []}

@app.get("/api/v1/health")
def get_health(dep: None = Depends(get_token_dep())):
    log.info('GET /api/v1/health')
    cfg = load_config()
    hosts = (cfg.get("health",{})).get("internet_hosts", [])
    lat = None
    if hosts:
        vals = [ping_ms(h) for h in hosts]
        vals = [v for v in vals if v is not None]
        if vals: lat = round(sum(vals)/len(vals), 1)
    st_cfg = (cfg.get("health",{})).get("speedtest",{})
    st = speedtest(st_cfg.get("binary")) if st_cfg.get("enabled", False) else None
    ipf = (cfg.get("health",{})).get("iperf3",{})
    ipres = iperf3_test(ipf.get("server")) if ipf.get("enabled", False) and ipf.get("server") else None
    return {"wan_latency_ms": lat, "speedtest": st, "iperf3": ipres}

@app.post("/api/v1/scan")
def run_scan(dep: None = Depends(get_token_dep())):
    log.info('POST /api/v1/scan')
    scan_cli()
    analyze_cli()
    return {"status": "ok"}

@app.post("/api/v1/analyze")
def run_analyze(dep: None = Depends(get_token_dep())):
    log.info('POST /api/v1/analyze')
    analyze_cli()
    return {"status": "ok"}

@app.get("/api/v1/threats")
def get_threats(dep: None = Depends(get_token_dep())):
    log.info('GET /api/v1/threats')
    # Placeholder; wire to your PA later.
    return {"items": [], "note": "Hook this to your Persistent Assistant threat feed."}

def main():
    import uvicorn
    uvicorn.run("src.server.api:app", host="0.0.0.0", port=8765, reload=False)

if __name__ == "__main__":
    main()
