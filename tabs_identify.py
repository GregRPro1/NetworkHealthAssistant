from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton, QComboBox
from PyQt6.QtCore import pyqtSignal
from nha_bridge import load_report_json

class IdentifyTab(QWidget):
    requestAi = pyqtSignal(dict)
    def __init__(self):
        super().__init__()
        self.cmb_device = QComboBox()
        self.txt_notes = QTextEdit(); self.txt_notes.setPlaceholderText("Notes/actions tried (power off, block, observe)...")
        self.btn_prompt = QPushButton("Ask AI to Identify"); self.btn_prompt.clicked.connect(self.on_prompt)
        layout = QVBoxLayout(); layout.addWidget(QLabel("Select a device:")); layout.addWidget(self.cmb_device); layout.addWidget(QLabel("Investigation notes (optional):")); layout.addWidget(self.txt_notes); layout.addWidget(self.btn_prompt); self.setLayout(layout)
        self.refresh_devices()

    def refresh_devices(self):
        report = load_report_json(); self.cmb_device.clear()
        for d in report.get("devices", []):
            label = f"{d.get('ip','?')}  {d.get('mac','?')}  {d.get('vendor','Unknown')}  {d.get('category','unknown')}"
            self.cmb_device.addItem(label, d)

    def on_prompt(self):
        d = self.cmb_device.currentData()
        if d is None: return
        payload = {"ip": d.get("ip"), "mac": d.get("mac"), "vendor": d.get("vendor"), "category": d.get("category"), "ports": d.get("ports", []), "notes": self.txt_notes.toPlainText().strip()}
        self.requestAi.emit(payload)
