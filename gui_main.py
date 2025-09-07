import sys, time
from PyQt6.QtWidgets import QApplication, QMainWindow, QTabWidget, QLabel, QStatusBar, QMessageBox
from PyQt6.QtGui import QPainter, QColor, QPixmap
from PyQt6.QtCore import Qt, QTimer

from styles import apply_dark_theme
from tabs_devices import DevicesTab
from tabs_identify import IdentifyTab
from tabs_tasks import TasksTab
from tabs_threats import ThreatsTab
from tabs_dashboard import DashboardTab
from tabs_settings import SettingsTab
from PyQt6.QtWidgets import QDialog, QTextBrowser, QVBoxLayout, QPushButton
from nha_bridge import load_report_json
from src.nha.net_health import ping_ms, speedtest, iperf3_test, tcp_open
from src.nha.config import load_config

class TrafficLight(QLabel):
    def __init__(self):
        super().__init__(); self._state = "grey"; self.setFixedWidth(28)
    def set_state(self, s: str): self._state = s; self.update()
    def paintEvent(self, e):
        super().paintEvent(e)
        pix = QPixmap(self.width(), self.height()); pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix); p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = {"red": QColor(220,70,70), "yellow": QColor(230,200,80), "green": QColor(90,200,90), "grey": QColor(120,120,120)}.get(self._state, QColor(120,120,120))
        p.setBrush(color); p.setPen(Qt.PenStyle.NoPen); d = min(self.width(), self.height()) - 6; p.drawEllipse(3,3,d,d); p.end(); self.setPixmap(pix)

def overall_state(summary):
    if not summary: return "grey"
    high = summary.get("risk_buckets",{}).get("high",0); med = summary.get("risk_buckets",{}).get("medium",0)
    if high > 0: return "red"
    if med > 0: return "yellow"
    return "green"

from PyQt6.QtCore import QThread, pyqtSignal

class HealthWorker(QThread):
    result = pyqtSignal(dict)
    def __init__(self, cfg):
        super().__init__(); self.cfg = cfg
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
            # Printers
            printers = (self.cfg.get("health",{})).get("printers", [])
            for p in printers:
                ip = p.get("ip"); name = p.get("name","Printer")
                online = False
                # Try common printer ports quickly: 9100 (RAW), 631 (IPP)
                if ip and (tcp_open(ip, 9100, 0.5) or tcp_open(ip, 631, 0.5)):
                    online = True
                res["printers"].append({"name": name, "ip": ip, "online": online})
        except Exception:
            pass
        self.result.emit(res)

class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Network Health Assistant"); self.resize(1100,700)
        tabs = QTabWidget(); self.dashboard = DashboardTab(); self.devices = DevicesTab(); self.identify = IdentifyTab(); self.tasks = TasksTab(); self.threats = ThreatsTab(); self.settings = SettingsTab()
        tabs.addTab(self.dashboard, "Dashboard"); tabs.addTab(self.devices, "Devices"); tabs.addTab(self.identify, "Identify"); tabs.addTab(self.tasks, "Tasks"); tabs.addTab(self.threats, "Threats/AI"); tabs.addTab(self.settings, "Settings")
        self.setCentralWidget(tabs)
        # Toolbar with icons
        from PyQt6.QtGui import QIcon
        tb = self.addToolBar("Main")
        tb.setMovable(False)
        act_scan = tb.addAction(QIcon("assets/icons/scan.svg"), "Scan Now", self.devices.on_scan)
        act_scan.setToolTip("Scan your network and refresh the Devices list")
        act_an = tb.addAction(QIcon("assets/icons/analyze.svg"), "Analyze", self.devices.on_analyze)
        act_an.setToolTip("Analyze risks and update Tasks & Dashboard")
        tb.addSeparator()
        # Auto-scan interval control
        from PyQt6.QtWidgets import QComboBox, QLabel
        tb.addWidget(QLabel(" Auto-scan: "))
        self.cmb_interval = QComboBox()
        self.cmb_interval.addItems(["Off","15 min","30 min","60 min"])
        tb.addWidget(self.cmb_interval)
        def apply_interval(idx):
            self.scan_timer.stop()
            val = self.cmb_interval.currentText()
            m = {"Off":0, "15 min":15, "30 min":30, "60 min":60}[val]
            if m>0: self.scan_timer.start(m*60*1000)
        self.cmb_interval.currentIndexChanged.connect(apply_interval)

        # Menu bar
        mb = self.menuBar()
        filem = mb.addMenu("&File")
        filem.addAction(QIcon("assets/icons/scan.svg"), "Scan Now", self.devices.on_scan)
        filem.addAction(QIcon("assets/icons/analyze.svg"), "Analyze", self.devices.on_analyze)
        filem.addSeparator()
        filem.addAction(QIcon("assets/icons/export.svg"), "Export Report (MD/JSON)", self.export_report)
        filem.addSeparator()
        filem.addAction("E&xit", self.close)

        viewm = mb.addMenu("&View")
        viewm.addAction(QIcon("assets/icons/dashboard.svg"), "Dashboard", lambda: tabs.setCurrentIndex(0))
        viewm.addAction(QIcon("assets/icons/devices.svg"), "Devices", lambda: tabs.setCurrentIndex(1))
        viewm.addAction(QIcon("assets/icons/identify.svg"), "Identify", lambda: tabs.setCurrentIndex(2))
        viewm.addAction(QIcon("assets/icons/tasks.svg"), "Tasks", lambda: tabs.setCurrentIndex(3))
        viewm.addAction(QIcon("assets/icons/threats.svg"), "Threats/AI", lambda: tabs.setCurrentIndex(4))
        viewm.addAction(QIcon("assets/icons/settings.svg"), "Settings", lambda: tabs.setCurrentIndex(5))

        toolsm = mb.addMenu("&Tools")
        toolsm.addAction(QIcon("assets/icons/settings.svg"), "Settings (config.yaml)", self.open_settings)
        toolsm.addAction(QIcon("assets/icons/timer.svg"), "Run Speed Test Now", self.run_speed_test)

        helpm = mb.addMenu("&Help")
        helpm.addAction(QIcon("assets/icons/about.svg"), "About", self.show_about)

        # Toolbar
        tb = self.addToolBar("Main")
        act_scan = tb.addAction("Scan Now")
        act_scan.triggered.connect(self.devices.on_scan)
        act_analyze = tb.addAction("Analyze")
        act_analyze.triggered.connect(self.devices.on_analyze)


        sb = QStatusBar(); self.light = TrafficLight(); self.lbl = QLabel("Security posture: —")
        from PyQt6.QtGui import QIcon
        icon_lbl = QLabel(); icon_lbl.setPixmap(QIcon("assets/icons/shield.svg").pixmap(18,18))
        sb.addPermanentWidget(icon_lbl)
        sb.addPermanentWidget(self.light)
        sb.addPermanentWidget(self.lbl, 1)
        self.lbl_wan = QLabel("WAN: — ms / — Mbps")
        sb.addPermanentWidget(self.lbl_wan)
        self.lbl_prn = QLabel("Printers: —")
        sb.addPermanentWidget(self.lbl_prn)
        self.setStatusBar(sb)

        self.devices.dataChanged.connect(self.on_report_changed)
        self.identify.requestAi.connect(self.on_ai_identify)
        self.threats.requestThreats.connect(self.on_fetch_threats)
        self.threats.requestAutoAdvice.connect(self.on_auto_advise)

        self.refresh_status()
        # Scan timer for auto-scan
        self.scan_timer = QTimer(self)
        self.scan_timer.setSingleShot(False)
        self.t = QTimer(self); self.t.timeout.connect(self.refresh_status); self.t.start(120*1000)
        # Auto-start interval Off
        self.health_timer = QTimer(self); self.health_timer.timeout.connect(self.kick_health_check); self.health_timer.start(5*60*1000)  # every 5 min
        # Auto-scan on launch
        self.devices.on_scan()


    def refresh_status(self):
        report = load_report_json(); s = report.get("summary", {}); st = overall_state(s)
        self.light.set_state(st)
        self.lbl.setText(f"Security posture: {st.upper()}  |  totals: {s.get('total',0)}, new: {s.get('new_devices',0)}  |  risk: H{s.get('risk_buckets',{}).get('high',0)} / M{s.get('risk_buckets',{}).get('medium',0)} / L{s.get('risk_buckets',{}).get('low',0)}")

    def on_report_changed(self, report: dict):
        self.statusBar().showMessage("Analysis complete. Tasks and dashboard updated.", 5000)
        self.refresh_status()

    def on_ai_identify(self, payload: dict):
        msg = f"""AI Identify (stub)

Device:
  IP: {payload.get('ip')}
  MAC: {payload.get('mac')}
  Vendor: {payload.get('vendor')}
  Category: {payload.get('category')}
  Ports: {', '.join(payload.get('ports', []))}

Next steps:
- Power-cycle suspected device, rescan to confirm mapping.
- Move to IoT/Guest SSID; rescan and validate isolation.
- Check router DHCP leases; label device in baseline.
- Block LAN for IoT; allow WAN only if needed; re-test apps.

(Replace with your Persistent Assistant AI response.)"""
        QMessageBox.information(self, "AI Identify", msg)

    def on_fetch_threats(self):
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        sample = f"""[{now}] Threat feed (stub)
- Review IoT camera CVEs (Xiaomi/Hikvision/TP-Link) last 30 days.
- Ensure router firmware up-to-date; UPnP/WPS disabled; WPA2/WPA3 only.
- Keep AVG & Malwarebytes updated; weekly quick + monthly full scans.
(Replace with live feed via PA web agent.)"""
        self.threats.show_text(sample)

    def on_auto_advise(self):
        self.devices.on_analyze()
        QMessageBox.information(self, "AI Advice", "Re-analysis complete. Wire this to PA to append tailored advice.")

def main():
    app = QApplication(sys.argv); apply_dark_theme(app); w = Main(); w.show(); sys.exit(app.exec())

if __name__ == "__main__":
    main()

    def export_report(self):
        # MD/JSON already in ./data; this is a simple notification
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(self, "Export Report", "Reports written to ./data/report.md and ./data/report.json")

    def open_settings(self):
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(self, "Settings", "Edit config.yaml to adjust paths and options.")

    def show_about(self):
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(self, "About", "Network Health Assistant\nDark UI, icons, dashboard, AI-ready.")


    def kick_health_check(self):
        cfg = load_config()
        self.hw = HealthWorker(cfg)
        self.hw.result.connect(self.update_health)
        self.hw.start()

    def update_health(self, res: dict):
        # WAN latency
        wan_latency = res.get("wan_latency_ms")
        st = res.get("wan_speed") or {}
        down = st.get("down_mbps"); up = st.get("up_mbps"); ping = st.get("ping_ms")

        wan_txt = "WAN: "
        wan_txt += (f"{wan_latency} ms" if wan_latency is not None else "— ms")
        wan_txt += " / "
        if down is not None and up is not None:
            wan_txt += f"{down}↓/{up}↑ Mbps"
        else:
            wan_txt += "— Mbps"
        self.lbl_wan.setText(wan_txt)

        # Printers
        prns = res.get("printers", [])
        if prns:
            parts = []
            for p in prns:
                parts.append(f"{p.get('name','Printer')}: {'Online' if p.get('online') else 'Offline'}")
            self.lbl_prn.setText("Printers: " + " | ".join(parts))
        else:
            self.lbl_prn.setText("Printers: —")

    def run_speed_test(self):
        # On-demand speed test
        cfg = load_config()
        st = speedtest(cfg.get('health',{}).get('speedtest',{}).get('binary'))
        if st:
            self.statusBar().showMessage(f"Speed test: {st.get('down_mbps')}↓/{st.get('up_mbps')}↑ Mbps, ping {st.get('ping_ms')} ms", 8000)
        else:
            self.statusBar().showMessage("Speed test failed or tool not installed.", 5000)

class HelpWindow(QDialog):
    def __init__(self, doc_path="docs/index.md"):
        super().__init__()
        self.setWindowTitle("Help & Documentation")
        self.resize(800, 600)
        from pathlib import Path
        layout = QVBoxLayout(self)
        self.viewer = QTextBrowser()
        try:
            with open(doc_path, "r", encoding="utf-8") as f:
                md = f.read()
            # very basic markdown-to-html fallback
            html = md.replace("\n\n", "<br/><br/>").replace("\n", "<br/>")
            self.viewer.setHtml(f"<html><body style='color:#ddd;background:#1e2022;font-family:Segoe UI, sans-serif'>{html}</body></html>")
        except Exception as e:
            self.viewer.setPlainText(f"Could not load documentation: {e}")
        layout.addWidget(self.viewer)
        btn = QPushButton("Close"); btn.clicked.connect(self.close)
        layout.addWidget(btn)
