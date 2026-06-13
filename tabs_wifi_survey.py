from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QCheckBox,
    QTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
)

from src.nha.config import load_config
from src.nha.wifi_survey import run_survey, save_observation, summarize


class WifiSurveyWorker(QThread):
    finished_ok = pyqtSignal(dict, dict)
    failed = pyqtSignal(str)

    def __init__(self, cfg: Dict[str, Any], location: str, internet_speed: bool, lan_iperf: bool, nas_test: bool):
        super().__init__()
        self.cfg = cfg
        self.location = location
        self.internet_speed = internet_speed
        self.lan_iperf = lan_iperf
        self.nas_test = nas_test

    def run(self):
        try:
            result = run_survey(
                self.cfg,
                location=self.location,
                run_internet_speed=self.internet_speed,
                run_lan_iperf=self.lan_iperf,
                run_nas_test=self.nas_test,
            )
            paths = save_observation(result, self.cfg)
            self.finished_ok.emit(result, paths)
        except Exception as exc:
            self.failed.emit(str(exc))


class WifiSurveyTab(QWidget):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.last_result: Dict[str, Any] = {}

        root = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Location"))
        self.ed_location = QLineEdit()
        self.ed_location.setPlaceholderText("Kitchen, summer house, garden patio...")
        top.addWidget(self.ed_location, 1)
        self.cb_speed = QCheckBox("Internet speed")
        self.cb_lan = QCheckBox("LAN iperf3")
        self.cb_nas = QCheckBox("NAS file test")
        top.addWidget(self.cb_speed)
        top.addWidget(self.cb_lan)
        top.addWidget(self.cb_nas)
        self.btn_capture = QPushButton("Capture Observation")
        top.addWidget(self.btn_capture)
        root.addLayout(top)

        self.lbl_status = QLabel("Ready")
        self.lbl_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.lbl_status)

        self.tbl = QTableWidget(0, 7)
        self.tbl.setHorizontalHeaderLabels(["Node", "BSSID", "SSID", "Signal", "Band", "Channel", "Radio"])
        self.tbl.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.tbl, 2)

        self.txt = QTextEdit()
        self.txt.setReadOnly(True)
        root.addWidget(self.txt, 1)

        btn_row = QHBoxLayout()
        self.btn_reload_cfg = QPushButton("Reload Config")
        self.btn_open_dir = QPushButton("Open Survey Folder")
        btn_row.addWidget(self.btn_reload_cfg)
        btn_row.addWidget(self.btn_open_dir)
        btn_row.addStretch()
        root.addLayout(btn_row)

        self.btn_capture.clicked.connect(self.on_capture)
        self.btn_reload_cfg.clicked.connect(self.reload_config)
        self.btn_open_dir.clicked.connect(self.open_survey_folder)

        survey = self.cfg.get("wifi_survey", {}) or {}
        self.cb_speed.setChecked(bool(survey.get("run_internet_speed_by_default", False)))
        self.cb_lan.setChecked(bool(survey.get("run_lan_iperf_by_default", False)))
        self.cb_nas.setChecked(bool(survey.get("run_nas_test_by_default", False)))

    def reload_config(self):
        self.cfg = load_config()
        self.lbl_status.setText("Config reloaded.")

    def _set_busy(self, busy: bool):
        self.btn_capture.setEnabled(not busy)
        self.btn_reload_cfg.setEnabled(not busy)
        self.btn_open_dir.setEnabled(not busy)
        self.lbl_status.setText("Running survey..." if busy else "Ready")

    def on_capture(self):
        self.reload_config()
        self._set_busy(True)
        self.worker = WifiSurveyWorker(
            self.cfg,
            self.ed_location.text(),
            self.cb_speed.isChecked(),
            self.cb_lan.isChecked(),
            self.cb_nas.isChecked(),
        )
        self.worker.finished_ok.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_done(self, result: Dict[str, Any], paths: Dict[str, str]):
        self._set_busy(False)
        self.last_result = result
        self.lbl_status.setText(f"Saved: {paths.get('json')}")
        self._populate(result)

    def _on_failed(self, error: str):
        self._set_busy(False)
        QMessageBox.critical(self, "Wi-Fi Survey", error)

    def _populate(self, result: Dict[str, Any]):
        current = result.get("wifi", {}).get("current", {}) or {}
        ssid = current.get("ssid")
        visible = [
            row for row in result.get("wifi", {}).get("visible_bssids", [])
            if not ssid or row.get("ssid") == ssid
        ]
        visible.sort(key=lambda row: int(row.get("signal_pct") or 0), reverse=True)

        self.tbl.setRowCount(0)
        active = current.get("bssid")
        for row in visible:
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)
            node = row.get("node_name") or ""
            if row.get("bssid") == active:
                node = f"* {node or 'Connected'}"
            values = [
                node,
                row.get("bssid", ""),
                row.get("ssid", ""),
                f"{row.get('signal_pct', '')}%",
                row.get("band", ""),
                row.get("channel", ""),
                row.get("radio_type", ""),
            ]
            for c, value in enumerate(values):
                self.tbl.setItem(r, c, QTableWidgetItem(str(value)))

        self.txt.setPlainText(self._summary_text(result))
        self.tbl.resizeColumnsToContents()

    def _summary_text(self, result: Dict[str, Any]) -> str:
        parts = [summarize(result), ""]
        latency = result.get("latency", {})
        parts.append("Internet latency:")
        for row in latency.get("internet", []):
            parts.append(f"- {row.get('target')}: {row.get('latency_ms')} ms")
        parts.append("")
        parts.append("LAN latency:")
        for row in latency.get("lan", []):
            parts.append(f"- {row.get('target')}: {row.get('latency_ms')} ms")

        throughput = result.get("throughput", {}) or {}
        internet = throughput.get("internet_speed")
        if internet:
            parts.append("")
            parts.append(
                f"Internet speed: {internet.get('down_mbps')} Mbps down / "
                f"{internet.get('up_mbps')} Mbps up, ping {internet.get('ping_ms')} ms"
            )
        lan = throughput.get("lan_iperf3")
        if lan:
            parts.append("")
            if lan.get("error"):
                parts.append(f"LAN iperf3: {lan.get('error')}")
            else:
                parts.append(f"LAN iperf3: {lan.get('lan_mbps')} Mbps")
        nas = throughput.get("nas_file")
        if nas:
            parts.append("")
            if nas.get("error"):
                parts.append(f"NAS file test: {nas.get('error')}")
            else:
                parts.append(
                    f"NAS file test ({nas.get('size_mb')} MB): "
                    f"{nas.get('write_mbps')} Mbps write / {nas.get('read_mbps')} Mbps read"
                )
        return "\n".join(parts)

    def open_survey_folder(self):
        survey = self.cfg.get("wifi_survey", {}) or {}
        path = Path(survey.get("output_dir") or "data/wifi_surveys")
        try:
            path.mkdir(parents=True, exist_ok=True)
        except Exception:
            path = Path("data/wifi_surveys")
            path.mkdir(parents=True, exist_ok=True)
        try:
            import os
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception:
            self.lbl_status.setText(str(path.resolve()))
