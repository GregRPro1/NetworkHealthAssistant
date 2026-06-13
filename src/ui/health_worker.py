# src/ui/health_worker.py
from __future__ import annotations
from PyQt6.QtCore import QThread, pyqtSignal
from src.nha.net_health import ping_ms, speedtest, iperf3_test, tcp_open

class HealthWorker(QThread):
    result = pyqtSignal(dict)
    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
    def run(self):
        res = {"wan_latency_ms": None, "wan_speed": None, "lan_speed": None, "printers": []}
        try:
            hosts = (self.cfg.get("health",{})).get("internet_hosts", [])
            if hosts:
                vals = [ping_ms(h) for h in hosts]
                vals = [v for v in vals if v is not None]
                if vals: res["wan_latency_ms"] = round(sum(vals)/len(vals), 1)
            st_cfg = (self.cfg.get("health",{})).get("speedtest",{})
            if st_cfg.get("enabled", False):
                res["wan_speed"] = speedtest(st_cfg.get("binary"))
            ipf = (self.cfg.get("health",{})).get("iperf3",{})
            if ipf.get("enabled", False) and ipf.get("server"):
                res["lan_speed"] = iperf3_test(ipf.get("server"))
            printers = (self.cfg.get("health",{})).get("printers", [])
            for p in printers:
                ip = p.get("ip"); name = p.get("name","Printer")
                online = False
                if ip and (tcp_open(ip, 9100, 0.5) or tcp_open(ip, 631, 0.5)):
                    online = True
                res["printers"].append({"name": name, "ip": ip, "online": online})
        except Exception:
            pass
        self.result.emit(res)
