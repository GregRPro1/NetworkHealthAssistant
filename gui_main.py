# gui_main.py
from __future__ import annotations
import sys, time, datetime, json, os, socket, subprocess, signal
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QLabel, QStatusBar, QMessageBox,
    QDialog, QVBoxLayout, QPushButton, QHBoxLayout, QFileDialog, QComboBox, QTextBrowser
)
from PyQt6.QtGui import QPainter, QColor, QPixmap, QIcon
from PyQt6.QtCore import Qt, QTimer

from styles import apply_theme
from tabs_devices import DevicesTab
from tabs_identify import IdentifyTab
from tabs_tasks import TasksTab
from tabs_threats import ThreatsTab
from tabs_dashboard import DashboardTab
from tabs_wifi_survey import WifiSurveyTab
from tabs_settings import SettingsTab

from src.nha.net_health import speedtest
from src.nha.config import load_config
from src.nha.registry import record_many
from src.integrations.deco_api import fetch_clients
from nha_bridge import load_report_json
from src.ui.health_worker import HealthWorker
from src.ui.help import HelpWindow

# ---------- helpers ----------
def safe_icon(path: str) -> QIcon:
    try:
        return QIcon(path) if os.path.exists(path) else QIcon()
    except Exception:
        return QIcon()

class TrafficLight(QLabel):
    def __init__(self):
        super().__init__()
        self._state = "grey"; self.setFixedWidth(28)
    def set_state(self, s: str): self._state = s; self.update()
    def paintEvent(self, e):
        super().paintEvent(e)
        pix = QPixmap(self.width(), self.height()); pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix); p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = {"red": QColor(220,70,70),"yellow": QColor(230,200,80),"green": QColor(90,200,90),"grey": QColor(120,120,120)}.get(self._state, QColor(120,120,120))
        p.setBrush(color); p.setPen(Qt.PenStyle.NoPen); d = min(self.width(), self.height()) - 6; p.drawEllipse(3,3,d,d); p.end(); self.setPixmap(pix)

def overall_state(summary: dict) -> str:
    if not summary: return "grey"
    rb = summary.get("risk_buckets",{}) or {}
    if rb.get("high",0)  > 0: return "red"
    if rb.get("medium",0)> 0: return "yellow"
    return "green"

# ---------- main window ----------
class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Network Health Assistant"); self.resize(1100, 700)

        # Tabs
        tabs = QTabWidget()
        self.dashboard = DashboardTab()
        self.devices   = DevicesTab()
        self.identify  = IdentifyTab()
        self.tasks     = TasksTab()
        self.threats   = ThreatsTab()
        self.wifi      = WifiSurveyTab()
        self.settings  = SettingsTab()
        tabs.addTab(self.dashboard, "Dashboard")
        tabs.addTab(self.devices,   "Devices")
        tabs.addTab(self.identify,  "Identify")
        tabs.addTab(self.tasks,     "Tasks")
        tabs.addTab(self.threats,   "Threats/AI")
        tabs.addTab(self.wifi,      "Wi-Fi Survey")
        tabs.addTab(self.settings,  "Settings")
        self.setCentralWidget(tabs)

        # Toolbar
        tb = self.addToolBar("Main"); tb.setMovable(False)
        tb.addAction(safe_icon("assets/icons/scan.svg"),    "Scan Now", self.devices.on_scan)
        tb.addAction(safe_icon("assets/icons/analyze.svg"), "Analyze",  self.devices.on_analyze)
        tb.addSeparator()
        tb.addWidget(QLabel(" Auto-scan: "))
        from PyQt6.QtWidgets import QComboBox
        self.cmb_interval = QComboBox(); self.cmb_interval.addItems(["Off","5 min","15 min","30 min","60 min"]); tb.addWidget(self.cmb_interval)
        self.scan_timer = QTimer(self); self.scan_timer.setSingleShot(False)
        self.cmb_interval.currentIndexChanged.connect(self._apply_interval)

        # Menubar
        mb = self.menuBar()
        m_file = mb.addMenu("&File")
        m_file.addAction(safe_icon("assets/icons/scan.svg"), "Scan Now", self.devices.on_scan)
        m_file.addAction(safe_icon("assets/icons/analyze.svg"), "Analyze", self.devices.on_analyze)
        m_file.addSeparator()
        m_file.addAction(safe_icon("assets/icons/export.svg"), "Export Report (MD/JSON)", self.export_report)
        m_file.addSeparator(); m_file.addAction("E&xit", self.close)

        m_view = mb.addMenu("&View")
        m_view.addAction(safe_icon("assets/icons/dashboard.svg"), "Dashboard", lambda: tabs.setCurrentIndex(0))
        m_view.addAction(safe_icon("assets/icons/devices.svg"),   "Devices",   lambda: tabs.setCurrentIndex(1))
        m_view.addAction(safe_icon("assets/icons/identify.svg"),  "Identify",  lambda: tabs.setCurrentIndex(2))
        m_view.addAction(safe_icon("assets/icons/tasks.svg"),     "Tasks",     lambda: tabs.setCurrentIndex(3))
        m_view.addAction(safe_icon("assets/icons/threats.svg"),   "Threats/AI",lambda: tabs.setCurrentIndex(4))
        m_view.addAction(safe_icon("assets/icons/scan.svg"),      "Wi-Fi Survey", lambda: tabs.setCurrentIndex(5))
        m_view.addAction(safe_icon("assets/icons/settings.svg"),  "Settings",  lambda: tabs.setCurrentIndex(6))

        m_tools = mb.addMenu("&Tools")
        m_tools.addAction(safe_icon("assets/icons/settings.svg"), "Settings (config.yaml)", self.open_settings)
        m_tools.addAction(safe_icon("assets/icons/timer.svg"),    "Run Speed Test Now",     self.run_speed_test)
        m_tools.addAction(safe_icon("assets/icons/scan.svg"),     "Capture Wi-Fi Survey",   self.wifi.on_capture)
        m_tools.addAction(safe_icon("assets/icons/diagnostics.svg"), "Diagnostics…",        self.open_diagnostics)
        m_tools.addSeparator()
        m_tools.addAction(safe_icon("assets/icons/server.svg"),   "Import Clients from Deco (Local API)", self.import_from_deco)
        m_tools.addSeparator()
        self.api_running = False
        self.act_api = m_tools.addAction(safe_icon("assets/icons/server.svg"), "API Server: Start", self.toggle_api_server)

        # Status bar
        sb = QStatusBar(); self.light = TrafficLight(); self.lbl = QLabel("Security posture: —")
        icon_lbl = QLabel(); icon_lbl.setPixmap(safe_icon("assets/icons/shield.svg").pixmap(18,18))
        sb.addPermanentWidget(icon_lbl); sb.addPermanentWidget(self.light); sb.addPermanentWidget(self.lbl, 1)
        self.lbl_wan = QLabel("WAN: — ms / — Mbps"); sb.addPermanentWidget(self.lbl_wan)
        self.lbl_prn = QLabel("Printers: —"); sb.addPermanentWidget(self.lbl_prn)
        self.lbl_ai = QLabel("AI: —")
        self.statusBar().addPermanentWidget(self.lbl_ai)
        self._set_ai_status()  # initial
        self.setStatusBar(sb)

        # Signals
        self.devices.dataChanged.connect(self.on_report_changed)
        self.identify.requestAi.connect(self.on_ai_identify)
        self.threats.requestThreats.connect(self.on_fetch_threats)
        self.threats.requestAutoAdvice.connect(self.on_auto_advise)
        self.settings.themeChanged.connect(self.set_theme)

        # Timers
        self.refresh_timer = QTimer(self); self.refresh_timer.timeout.connect(self.refresh_status); self.refresh_timer.start(120*1000)
        self.health_timer  = QTimer(self); self.health_timer.timeout.connect(self.kick_health_check); self.health_timer.start(5*60*1000)

        # Do an immediate health check on startup
        self.kick_health_check()

        # Start API server if not running
        self.ensure_api_server()

        # Initial actions (deferred)
        from PyQt6.QtCore import QTimer as _QTimer
        _QTimer.singleShot(300, self.devices.on_scan)
        _QTimer.singleShot(1000, self.refresh_status)

    # ---------- helpers ----------
    def _apply_interval(self, _):
        self.scan_timer.stop()
        val = self.cmb_interval.currentText()
        m = {"Off":0,"5 min":5,"15 min":15,"30 min":30,"60 min":60}[val]
        if m>0: self.scan_timer.start(m*60*1000)

    def _set_ai_status(self):
        """Green when a plausible AI backend is configured, grey otherwise."""
        try:
            cfg = load_config()
            token = (cfg.get("api", {}) or {}).get("token", "")
            ok = bool(token and token != "changeme-very-secret")
        except Exception:
            ok = False
        if ok:
            self.lbl_ai.setText("AI: ready")
        else:
            self.lbl_ai.setText("AI: not configured")

    # ---------- API server mgmt ----------
    def _port_open(self, host: str, port: int, timeout: float = 0.4) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout): return True
        except OSError: return False

    def ensure_api_server(self):
        self._api_proc = None
        host, port = "127.0.0.1", 8765
        if self._port_open(host, port):
            self.statusBar().showMessage("API server already running on http://127.0.0.1:8765", 5000)
            return
        try:
            creationflags = 0
            if os.name == "nt":
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            self._api_proc = subprocess.Popen([sys.executable, "-m", "src.server.api"],
                                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                              creationflags=creationflags)
            self.api_running = True; self.act_api.setText("API Server: Stop")
            self.statusBar().showMessage("API server started on http://127.0.0.1:8765", 5000)
        except Exception as e:
            self.statusBar().showMessage(f"Failed to start API server: {e}", 8000)

    def toggle_api_server(self):
        if not getattr(self, "_api_proc", None):
            self.ensure_api_server()
        else:
            try:
                if os.name == "nt":
                    self._api_proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
                self._api_proc.terminate()
            except Exception: pass
            finally:
                self._api_proc = None; self.api_running = False
                self.act_api.setText("API Server: Start")
                self.statusBar().showMessage("API server stopped.", 4000)

    def closeEvent(self, event):
        try:
            if getattr(self, "_api_proc", None):
                if os.name == "nt":
                    self._api_proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
                self._api_proc.terminate()
        except Exception: pass
        super().closeEvent(event)

    # ---------- UI actions ----------
    def set_theme(self, mode: str):
        apply_theme(QApplication.instance(), mode or "dark")
        self.statusBar().showMessage(f"Theme switched to {mode}", 3000)

    def refresh_status(self):
        report = load_report_json(); s = report.get("summary", {})
        st = overall_state(s); self.light.set_state(st)
        self.lbl.setText(
            f"Security posture: {st.upper()}  |  totals: {s.get('total',0)}, new: {s.get('new_devices',0)}  |  "
            f"risk: H{s.get('risk_buckets',{}).get('high',0)} / "
            f"M{s.get('risk_buckets',{}).get('medium',0)} / "
            f"L{s.get('risk_buckets',{}).get('low',0)}"
        )
        if s.get("total", 0) == 0:
            self.statusBar().showMessage("No devices yet — on Windows, run VS Code as Administrator and install Npcap + nmap; then File → Scan Now.", 8000)

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

(Replace with Persistent Assistant AI response.)
"""
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

    def export_report(self):
        data_dir = Path("data"); report_json = data_dir / "report.json"
        if not report_json.exists():
            QMessageBox.warning(self, "Export Report", "No report found yet. Run Scan/Analyze first."); return
        try:
            rep = json.loads(report_json.read_text(encoding="utf-8"))
        except Exception as e:
            QMessageBox.critical(self, "Export Report", f"Failed to read report.json: {e}"); return

        s = rep.get("summary", {}); actions = rep.get("actions", []); devices = rep.get("devices", [])
        lines = []
        lines.append("# Network Health Assistant Report")
        lines.append(f"_Generated: {datetime.datetime.now().isoformat(timespec='seconds')}_\n")
        lines.append("## Summary")
        lines.append(f"- Total devices: **{s.get('total', 0)}**")
        lines.append(f"- New devices: **{s.get('new_devices', 0)}**")
        rb = s.get("risk_buckets", {})
        lines.append(f"- Risk: High **{rb.get('high',0)}**, Medium **{rb.get('medium',0)}**, Low **{rb.get('low',0)}**\n")
        if actions:
            lines.append("## Actions")
            for a in sorted(actions, key=lambda x: x.get("priority", 99)):
                lines.append(f"- **P{a.get('priority',99)}** {a.get('title','')} — {a.get('detail','')}")
        if devices:
            lines.append("\n## Devices")
            lines.append("| IP | MAC | Vendor | Category | Risk | Hostname |")
            lines.append("|---|---|---|---|---:|---|")
            for d in devices:
                lines.append(f"| {d.get('ip','')} | {d.get('mac','')} | {d.get('vendor','')} | {d.get('category','')} | {d.get('risk_score',0)} | {d.get('hostname','')} |")

        default_md = str((data_dir / "report_export.md").resolve())
        out_path, _ = QFileDialog.getSaveFileName(self, "Save Markdown", default_md, "Markdown (*.md)")
        if not out_path: return
        try:
            Path(out_path).write_text("\n".join(lines), encoding="utf-8")
            QMessageBox.information(self, "Export Report", f"Saved:\n{out_path}\n\nJSON source:\n{report_json.resolve()}")
        except Exception as e:
            QMessageBox.critical(self, "Export Report", f"Failed to write markdown: {e}")

    def open_diagnostics(self):
        try:
            self.devices.show_diagnostics_dialog("Environment diagnostics")
        except Exception as e:
            QMessageBox.warning(self, "Diagnostics", f"Diagnostics not available: {e}")

    def open_settings(self):
        tabs: QTabWidget = self.centralWidget(); tabs.setCurrentIndex(6)
        self.statusBar().showMessage("Opened Settings tab (edit config.yaml here).", 4000)

    def show_about(self):
        QMessageBox.information(self, "About", "Network Health Assistant\nDark UI, icons, dashboard, AI-ready.\n© GR-Analysis")

    def kick_health_check(self):
        cfg = load_config(); self.hw = HealthWorker(cfg)
        self.hw.result.connect(self.update_health); self.hw.start()

    def update_health(self, res: dict):
        wan_latency = res.get("wan_latency_ms"); st = res.get("wan_speed") or {}
        down = st.get("down_mbps"); up = st.get("up_mbps")
        wan_txt = "WAN: " + (f"{wan_latency} ms" if wan_latency is not None else "— ms") + " / "
        wan_txt += f"{down}↓/{up}↑ Mbps" if (down is not None and up is not None) else "— Mbps"
        self.lbl_wan.setText(wan_txt)
        prns = res.get("printers", [])
        self.lbl_prn.setText("Printers: " + " | ".join(f"{p.get('name','Printer')}: {'Online' if p.get('online') else 'Offline'}" for p in prns) if prns else "Printers: —")

    def run_speed_test(self):
        try: cfg = load_config()
        except Exception: cfg = {}
        st_cfg = (cfg.get("health", {}) or {}).get("speedtest", {}) or {}
        res = speedtest(st_cfg.get("binary") or "speedtest")
        if not res:
            self.statusBar().showMessage("Speed test failed (missing tool or no internet). Install Ookla 'speedtest' or 'speedtest-cli' and set path in Settings.", 8000); return
        down = res.get("down_mbps"); up = res.get("up_mbps"); ping = res.get("ping_ms")
        self.statusBar().showMessage(f"Speed test: {down}↓/{up}↑ Mbps, ping {ping} ms", 8000)
        wan_txt = "WAN: " + (f"{ping} ms" if ping is not None else "— ms") + " / " + (f"{down}↓/{up}↑ Mbps" if (down is not None and up is not None) else "— Mbps")
        self.lbl_wan.setText(wan_txt)

    def import_from_deco(self):
        try:
            cfg = load_config()
            deco_cfg = (cfg.get("integrations", {}) or {}).get("deco", {}) or {}
            if not deco_cfg.get("enabled"):
                QMessageBox.information(self, "Deco Import", "Deco integration is disabled in config.yaml."); return
            clients = fetch_clients(deco_cfg)
            if not clients:
                QMessageBox.information(self, "Deco Import", "No clients returned by Deco Local API (supply credentials or check host)."); return
            ip_to_sources = {c.get("ip"): ["deco-api"] for c in clients if c.get("ip")}
            record_many(clients, segment="deco", sources_map=ip_to_sources)
            Path("data").mkdir(parents=True, exist_ok=True)
            Path("data/deco_clients.json").write_text(json.dumps(clients, indent=2), encoding="utf-8")
            self.devices.on_analyze()
            self.statusBar().showMessage(f"Imported {len(clients)} clients from Deco.", 6000)
        except Exception as e:
            QMessageBox.critical(self, "Deco Import", f"Failed to import from Deco: {e}")

# ---------- app entry ----------
def main():
    app = QApplication(sys.argv)
    try:
        cfg = load_config(); mode = (cfg.get("ui", {}) or {}).get("theme", "dark")
    except Exception:
        mode = "dark"
    apply_theme(app, mode)
    w = Main(); w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
