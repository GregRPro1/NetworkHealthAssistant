import os, shutil, yaml, socket, struct, platform
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QTableWidget, QTableWidgetItem, QGroupBox, QFileDialog, QMessageBox, QCheckBox, QSpinBox)
from PyQt6.QtCore import Qt
from src.nha.config import load_config
from src.nha.net_health import tcp_open
from nha_bridge import load_report_json

def _default_gateway():
    # Simple cross-platform best-effort
    try:
        if platform.system().lower().startswith("win"):
            import subprocess, re
            out = subprocess.check_output(["ipconfig"], text=True, timeout=5)
            gw = None
            block = ""
            for line in out.splitlines():
                if "Default Gateway" in line and ":" in line:
                    cand = line.split(":")[-1].strip()
                    if cand and cand != "0.0.0.0":
                        gw = cand; break
            return gw
        else:
            import subprocess
            out = subprocess.check_output(["ip", "route"], text=True, timeout=5)
            for line in out.splitlines():
                if line.startswith("default via "):
                    return line.split()[2]
    except Exception:
        pass
    return None

class SettingsTab(QWidget):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.setLayout(self._build_ui())

    def _build_ui(self):
        layout = QVBoxLayout()

        # AI group
        g_ai = QGroupBox("AI / Persistent Assistant")
        ai_l = QVBoxLayout()
        self.ed_pa_path = QLineEdit(self.cfg.get("ai",{}).get("persistent_assistant_path", ""))
        self.ed_entry = QLineEdit(self.cfg.get("ai",{}).get("entrypoint","pa.ai_client:analyze_inventory"))
        ai_l.addWidget(QLabel("Persistent Assistant path:"))
        ai_l.addWidget(self.ed_pa_path)
        ai_l.addWidget(QLabel("Entrypoint (module:function):"))
        ai_l.addWidget(self.ed_entry)
        g_ai.setLayout(ai_l)

        # Health group
        g_h = QGroupBox("Health Checks")
        h_l = QVBoxLayout()
        # Internet hosts
        self.ed_hosts = QLineEdit(", ".join(self.cfg.get("health",{}).get("internet_hosts", ["1.1.1.1","8.8.8.8"])))
        self.ed_router = QLineEdit(", ".join(self.cfg.get("health",{}).get("lan_targets", ["192.168.1.1"])))
        # Speedtest
        st = self.cfg.get("health",{}).get("speedtest",{})
        self.cb_st = QCheckBox("Enable speedtest")
        self.cb_st.setChecked(bool(st.get("enabled", True)))
        self.ed_st_bin = QLineEdit(st.get("binary","speedtest"))
        self.sp_st_int = QSpinBox(); self.sp_st_int.setRange(5, 1440); self.sp_st_int.setValue(int(st.get("interval_min",120)))
        # iperf3
        ipf = self.cfg.get("health",{}).get("iperf3",{})
        self.cb_ipf = QCheckBox("Enable iperf3 LAN throughput")
        self.cb_ipf.setChecked(bool(ipf.get("enabled", False)))
        self.ed_ipf_server = QLineEdit(ipf.get("server",""))

        h_l.addWidget(QLabel("Internet hosts (comma-separated):"))
        h_l.addWidget(self.ed_hosts)
        h_l.addWidget(QLabel("LAN/router targets (comma-separated):"))
        h_l.addWidget(self.ed_router)
        h_l.addWidget(self.cb_st); h_l.addWidget(QLabel("Speedtest binary (speedtest / speedtest-cli):")); h_l.addWidget(self.ed_st_bin)
        h_l.addWidget(QLabel("Speedtest interval (minutes):")); h_l.addWidget(self.sp_st_int)
        h_l.addWidget(self.cb_ipf); h_l.addWidget(QLabel("iperf3 server (LAN host running `iperf3 -s`):")); h_l.addWidget(self.ed_ipf_server)
        g_h.setLayout(h_l)

        # Printers table
        g_p = QGroupBox("Printers")
        p_l = QVBoxLayout()
        self.tbl_prn = QTableWidget(0, 2)
        self.tbl_prn.setHorizontalHeaderLabels(["Name","IP"])
        self.tbl_prn.horizontalHeader().setStretchLastSection(True)
        for p in self.cfg.get("health",{}).get("printers", []):
            self._add_printer_row(p.get("name","Printer"), p.get("ip",""))
        btn_add = QPushButton("Add Printer"); btn_add.clicked.connect(lambda: self._add_printer_row("New Printer",""))
        p_l.addWidget(self.tbl_prn); p_l.addWidget(btn_add)
        g_p.setLayout(p_l)

        # Buttons row
        row = QHBoxLayout()
        self.btn_detect = QPushButton("Detect")
        self.btn_detect.clicked.connect(self.on_detect)
        self.btn_save = QPushButton("Save Settings")
        self.btn_save.clicked.connect(self.on_save)
        self.btn_export = QPushButton("Export IoT Inventory for Home Assistant")
        self.btn_export.clicked.connect(self.on_export_iot)
        row.addWidget(self.btn_detect); row.addWidget(self.btn_save); row.addStretch(); row.addWidget(self.btn_export)

        layout.addWidget(g_ai)
        layout.addWidget(g_h)
        layout.addWidget(g_p)
        layout.addLayout(row)
        layout.addStretch()
        return layout

    def _add_printer_row(self, name, ip):
        r = self.tbl_prn.rowCount(); self.tbl_prn.insertRow(r)
        self.tbl_prn.setItem(r, 0, QTableWidgetItem(name))
        self.tbl_prn.setItem(r, 1, QTableWidgetItem(ip))

    def on_detect(self):
        # Router/default gateway guess
        gw = _default_gateway()
        if gw:
            self.ed_router.setText(gw)
        # Internet hosts defaults
        self.ed_hosts.setText("1.1.1.1, 8.8.8.8")
        # Speedtest binary guess
        b = shutil.which("speedtest") or shutil.which("speedtest-cli") or "speedtest"
        self.ed_st_bin.setText(b)
        # Printers: try to infer from current report by checking port 9100/631 online
        report = load_report_json()
        devices = report.get("devices", [])
        found = []
        for d in devices:
            ip = d.get("ip")
            if not ip: continue
            if tcp_open(ip, 9100, 0.2) or tcp_open(ip, 631, 0.2):
                found.append({"name": f"Printer@{ip}", "ip": ip})
        if found:
            self.tbl_prn.setRowCount(0)
            for p in found:
                self._add_printer_row(p["name"], p["ip"])
        QMessageBox.information(self, "Detect", "Attempted to detect defaults. Please review and Save.")

    def on_save(self):
        # Build YAML
        try:
            hosts = [x.strip() for x in self.ed_hosts.text().split(",") if x.strip()]
            lan = [x.strip() for x in self.ed_router.text().split(",") if x.strip()]
            printers = []
            for r in range(self.tbl_prn.rowCount()):
                name = self.tbl_prn.item(r,0).text().strip() if self.tbl_prn.item(r,0) else ""
                ip = self.tbl_prn.item(r,1).text().strip() if self.tbl_prn.item(r,1) else ""
                if ip: printers.append({"name": name or f"Printer@{ip}", "ip": ip})
            data = self.cfg  # start from loaded cfg to preserve other keys
            data.setdefault("ai",{})
            data["ai"]["persistent_assistant_path"] = self.ed_pa_path.text().strip()
            data["ai"]["entrypoint"] = self.ed_entry.text().strip()
            data.setdefault("health",{})
            data["health"]["internet_hosts"] = hosts or ["1.1.1.1","8.8.8.8"]
            data["health"]["lan_targets"] = lan or ["192.168.1.1"]
            data["health"]["printers"] = printers
            data["health"]["speedtest"] = {
                "enabled": self.cb_st.isChecked(),
                "interval_min": int(self.sp_st_int.value()),
                "binary": self.ed_st_bin.text().strip() or "speedtest"
            }
            data["health"]["iperf3"] = {
                "enabled": self.cb_ipf.isChecked(),
                "server": self.ed_ipf_server.text().strip()
            }
            with open("config.yaml","w",encoding="utf-8") as f:
                yaml.safe_dump(data, f, sort_keys=False)
            QMessageBox.information(self, "Saved", "Settings saved to config.yaml")
            self.cfg = data
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save settings: {e}")

    def on_export_iot(self):
        report = load_report_json()
        devices = report.get("devices", [])
        iot = [{
            "ip": d.get("ip"),
            "mac": d.get("mac"),
            "vendor": d.get("vendor"),
            "category": d.get("category"),
            "hostname": d.get("hostname"),
        } for d in devices if d.get("category","").startswith("iot") or "camera" in d.get("category","")]
        if not iot:
            QMessageBox.information(self, "Export IoT", "No IoT/camera devices identified in current report. Run Analyze first.")
            return
        # Write JSON and YAML versions
        out_dir = "data"
        os.makedirs(out_dir, exist_ok=True)
        import json
        with open(os.path.join(out_dir, "home_assistant_iot.json"), "w", encoding="utf-8") as f:
            json.dump({"devices": iot}, f, indent=2)
        try:
            with open(os.path.join(out_dir, "home_assistant_iot.yaml"), "w", encoding="utf-8") as f:
                yaml.safe_dump({"devices": iot}, f, sort_keys=False)
        except Exception:
            pass
        QMessageBox.information(self, "Export IoT", "Exported IoT inventory to data/home_assistant_iot.(json|yaml).\nFor HA, you can ingest this via a simple integration or scripts.")
