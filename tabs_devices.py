# tabs_devices.py
from __future__ import annotations
import json, time
from pathlib import Path

from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, QVariant, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTableView, QDialog, QTextEdit, QListWidget, QListWidgetItem
)

from src.nha.scanner import run_scan_iter
from src.nha.analyze import analyze
from src.nha.logger import get_logger
from nha_bridge import load_report_json

log = get_logger("ui.devices")

# ------------ Busy overlay ------------
from PyQt6.QtWidgets import QFrame, QProgressBar

class BusyOverlay(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            "QFrame { background: rgba(0,0,0,140); border: 0px; }"
            "QLabel { color: #ddd; }"
            "QListWidget { background: rgba(30,32,34,200); color:#ddd; border:1px solid #3c3f41; }"
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setVisible(False)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl = QLabel("Working…")
        self.pbar = QProgressBar()
        self.pbar.setRange(0, 0)  # marquee by default
        self.note = QLabel("")
        self.stage_list = QListWidget()
        self.stage_list.setMaximumWidth(520)
        lay.addWidget(self.lbl)
        lay.addWidget(self.pbar)
        lay.addWidget(self.note)
        lay.addWidget(self.stage_list)

        # progress bookkeeping
        self._t0 = None
        self._last_rate = None  # items/sec

        self._stages = [
            "Reading ARP cache",
            "nmap host discovery",
            "ICMP sweep",
            "TCP probe",
            "UPnP/SSDP discovery",
            "mDNS discovery",
            "Marking Deco nodes",
            "Merging Deco clients",
            "Saving results",
            "Recording registry",
        ]
        for s in self._stages:
            QListWidgetItem(f"□ {s}", self.stage_list)

    def _set_stage_done(self, name: str):
        for i in range(self.stage_list.count()):
            text = self.stage_list.item(i).text()
            if text.endswith(name):
                self.stage_list.item(i).setText(f"✔ {name}")
                break

    def show_stage(self, title: str, note: str = "", *, done: int = 0, total: int = 0):
        # Initialize timing
        if self._t0 is None:
            self._t0 = time.time()
        self.lbl.setText(title)
        # counters + ETA for long loops
        if total and total > 0:
            now = time.time()
            rate = done / max(0.001, (now - self._t0))
            # EMA smooth
            self._last_rate = rate if self._last_rate is None else (0.3*rate + 0.7*self._last_rate)
            remaining = max(0, total - done)
            eta_s = int(remaining / max(0.01, self._last_rate))
            mm, ss = divmod(eta_s, 60)
            self.pbar.setRange(0, total)
            self.pbar.setValue(min(done, total))
            self.note.setText(f"{note}  [{done}/{total}]  ETA ~ {mm:02d}:{ss:02d}")
        else:
            self.pbar.setRange(0, 0)
            self.note.setText(note)

        if not self.isVisible():
            self.resize(self.parent().size())
            self.setVisible(True)

    def mark_completed(self, pretty_name: str):
        self._set_stage_done(pretty_name)

    def reset(self):
        self._t0 = None
        self._last_rate = None
        self.stage_list.clear()
        for s in self._stages:
            QListWidgetItem(f"□ {s}", self.stage_list)

    def hide_now(self):
        self.setVisible(False)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.parent():
            self.resize(self.parent().size())
            self.move(0, 0)

# ------------- model -------------
COLUMNS = [
    ("ip","IP"), ("mac","MAC"), ("vendor","Vendor"),
    ("hostname","Hostname"), ("category","Category"),
    ("ssid","SSID"), ("vlan_id","VLAN"),
    ("risk_score","Risk"), ("issues","Reasons"),
]

class DevicesModel(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self.rows = []

    def setRows(self, rows):
        self.beginResetModel()
        self.rows = rows or []
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return COLUMNS[section][1]
        return QVariant()

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return QVariant()
        k = COLUMNS[index.column()][0]
        v = self.rows[index.row()].get(k, "")
        if k == "issues" and isinstance(v, list):
            return ", ".join(v)
        if k == "vlan_id" and v is None:
            return ""
        return str(v)

# ------------- worker thread -------------

class ScanWorker(QThread):
    progress = pyqtSignal(str, int, int, str)  # stage, done, total, note
    finished_ok = pyqtSignal(dict)             # report dict
    failed = pyqtSignal(str)

    def run(self):
        try:
            # drive progressive scan
            def cb(stage, done, total, note):
                self.progress.emit(stage, int(done), int(total), note or "")

            for stage, payload in run_scan_iter(progress=cb):
                if stage in ("begin","arp","nmap","icmp_tcp","ssdp","mdns","deco_mark","deco_merge","save","record"):
                    self.progress.emit(stage, 0, 0, json.dumps(payload))
            # analyze
            data_dir = Path("data")
            cur = json.loads((data_dir / "current_scan.json").read_text(encoding="utf-8")) if (data_dir / "current_scan.json").exists() else []
            base = json.loads((data_dir / "baseline.json").read_text(encoding="utf-8")) if (data_dir / "baseline.json").exists() else []
            analyzed, summary = analyze({"devices": cur}, {"devices": base})
            rep = {"devices": analyzed, "summary": summary}
            (data_dir / "report.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
            self.finished_ok.emit(rep)
        except Exception as e:
            self.failed.emit(str(e))

# ------------- main tab -------------

class DevicesTab(QWidget):
    dataChanged = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.model = DevicesModel()
        self._all_rows = []

        v = QVBoxLayout(self)
        # toolbar
        row = QHBoxLayout()
        self.btn_scan = QPushButton("Scan Now")
        self.btn_analyze = QPushButton("Analyze")
        self.btn_diag = QPushButton("Diagnostics…")
        row.addWidget(self.btn_scan); row.addWidget(self.btn_analyze); row.addStretch(); row.addWidget(self.btn_diag)
        v.addLayout(row)

        # table
        self.tbl = QTableView(); self.tbl.setModel(self.model)
        self.table = self.tbl
        self.tbl.setSortingEnabled(True)
        v.addWidget(self.tbl)

        # overlay
        self.busy = BusyOverlay(self)

        # signals
        self.btn_scan.clicked.connect(self.on_scan)
        self.btn_analyze.clicked.connect(self.on_analyze)
        self.btn_diag.clicked.connect(lambda: self.show_diagnostics_dialog("Environment diagnostics"))

        # populate from existing report if present
        try:
            rep = load_report_json()
            self._all_rows = rep.get("devices", [])
            self.model.setRows(self._all_rows)
        except Exception:
            pass

    # -------- actions --------

    def on_scan(self):
        self.busy.reset()
        self.busy.show_stage("Preparing", "Starting")
        self.btn_scan.setEnabled(False); self.btn_analyze.setEnabled(False)
        self.w = ScanWorker()
        self.w.progress.connect(self._on_progress)
        self.w.finished_ok.connect(self._on_scan_done)
        self.w.failed.connect(self._on_scan_failed)
        self.w.start()

    def _on_progress(self, stage: str, done: int, total: int, note: str):
        # stage can be 'begin','arp','nmap','icmp','tcp','icmp_tcp','ssdp','mdns','deco_mark','deco_merge','save','record'
        title_map = {
            "begin": "Preparing",
            "arp": "Reading ARP cache",
            "nmap": "nmap host discovery",
            "icmp": "ICMP sweep",
            "tcp": "TCP probe",
            "icmp_tcp": "ICMP/TCP sweep",
            "ssdp": "UPnP/SSDP discovery",
            "mdns": "mDNS discovery",
            "deco_mark": "Marking Deco nodes",
            "deco_merge": "Merging Deco clients",
            "save": "Saving results",
            "record": "Recording registry",
        }
        title = title_map.get(stage, "Working…")

        # Which box should flip to “done”?
        completed_name = None
        if stage in ("arp",): completed_name = "Reading ARP cache"
        elif stage in ("nmap",): completed_name = "nmap host discovery"
        elif stage in ("icmp_tcp",): completed_name = "ICMP sweep"  # ICMP/TCP sequence completes both
        elif stage in ("ssdp",): completed_name = "UPnP/SSDP discovery"
        elif stage in ("mdns",): completed_name = "mDNS discovery"
        elif stage in ("deco_mark",): completed_name = "Marking Deco nodes"
        elif stage in ("deco_merge",): completed_name = "Merging Deco clients"
        elif stage in ("save",): completed_name = "Saving results"
        elif stage in ("record",): completed_name = "Recording registry"

        if completed_name:
            self.busy.mark_completed(completed_name)

        # For icmp/tcp we do meaningful counters/ETA
        show_done, show_total = (done, total) if stage in ("icmp", "tcp") and total else (0, 0)
        self.busy.show_stage(title, note, done=show_done, total=show_total)

    def _on_scan_done(self, report: dict):
        self.busy.hide_now()
        self.btn_scan.setEnabled(True); self.btn_analyze.setEnabled(True)
        self._all_rows = report.get("devices", [])
        self.model.setRows(self._all_rows)
        self.dataChanged.emit(report)
        # Proactively re-run analysis-derived widgets if your dashboard/tasks expose refresh() methods
        try:
            # parent is Main -> centralWidget() is QTabWidget
            main = self.window()
            if hasattr(main, "dashboard") and hasattr(main.dashboard, "refresh_dashboard"):
                main.dashboard.refresh_dashboard()
            if hasattr(main, "tasks") and hasattr(main.tasks, "reload_from_report"):
                main.tasks.reload_from_report()
        except Exception:
            pass

    def _on_scan_failed(self, err: str):
        self.busy.hide_now()
        self.btn_scan.setEnabled(True); self.btn_analyze.setEnabled(True)
        self.show_diagnostics_dialog(f"Scan error: {err}")

    def on_analyze(self):
        try:
            data_dir = Path("data")
            cur = json.loads((data_dir / "current_scan.json").read_text(encoding="utf-8")) if (data_dir / "current_scan.json").exists() else []
            base = json.loads((data_dir / "baseline.json").read_text(encoding="utf-8")) if (data_dir / "baseline.json").exists() else []
            analyzed, summary = analyze({"devices": cur}, {"devices": base})
            rep = {"devices": analyzed, "summary": summary}
            (data_dir / "report.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
            self._all_rows = analyzed
            self.model.setRows(analyzed)
            self.dataChanged.emit(rep)
        except Exception as e:
            self.show_diagnostics_dialog(f"Analyze error: {e}")

    def apply_filter(self):
        return None

    # -------- diagnostics --------

    def show_diagnostics_dialog(self, reason: str = ""):
        dlg = QDialog(self); dlg.setWindowTitle("Diagnostics")
        lay = QVBoxLayout(dlg)
        txt = QTextEdit(); txt.setReadOnly(True)
        info = []
        info.append(f"Reason: {reason}")
        p = Path("data/current_scan.json")
        info.append(f"current_scan.json exists: {p.exists()} size={p.stat().st_size if p.exists() else 0}")
        p = Path("data/report.json")
        info.append(f"report.json exists: {p.exists()} size={p.stat().st_size if p.exists() else 0}")
        info.append("Tips:")
        info.append("- Windows: run VS Code as Administrator; install Npcap & nmap.")
        info.append("- Ensure CIDR in config.yaml matches your LAN.")
        info.append("- Use Tools → Import Clients from Deco to close the gap with the Deco app count.")
        txt.setPlainText("\n".join(info))
        lay.addWidget(txt)
        btn = QPushButton("Close"); btn.clicked.connect(dlg.accept)
        lay.addWidget(btn)
        dlg.resize(640, 420)
        dlg.exec()
