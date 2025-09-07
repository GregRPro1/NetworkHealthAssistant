from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QTextEdit, QLabel, QSpinBox, QHBoxLayout
from PyQt6.QtCore import QTimer, pyqtSignal

class ThreatsTab(QWidget):
    requestThreats = pyqtSignal()
    requestAutoAdvice = pyqtSignal()
    def __init__(self):
        super().__init__()
        self.txt = QTextEdit(); self.txt.setReadOnly(True)
        self.btn_fetch = QPushButton("Fetch Latest Threat Intel (AI)"); self.btn_fetch.clicked.connect(lambda: self.requestThreats.emit())
        self.btn_advise = QPushButton("Re-run AI Advice"); self.btn_advise.clicked.connect(lambda: self.requestAutoAdvice.emit())
        self.spin_mins = QSpinBox(); self.spin_mins.setRange(5,720); self.spin_mins.setValue(60)
        self.timer = QTimer(self); self.timer.timeout.connect(lambda: self.requestThreats.emit())
        btn_apply = QPushButton("Apply"); btn_apply.clicked.connect(self.apply_interval)

        top = QHBoxLayout(); top.addWidget(QLabel("Auto-fetch every (min):")); top.addWidget(self.spin_mins); top.addWidget(btn_apply); top.addStretch(); top.addWidget(self.btn_fetch); top.addWidget(self.btn_advise)
        layout = QVBoxLayout(); layout.addLayout(top); layout.addWidget(self.txt); self.setLayout(layout)

    def apply_interval(self):
        self.timer.stop(); self.timer.start(self.spin_mins.value() * 60 * 1000)

    def show_text(self, text: str):
        self.txt.setPlainText(text)
