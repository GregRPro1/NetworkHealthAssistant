from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QPushButton
from nha_bridge import load_report_json

class TasksTab(QWidget):
    def __init__(self):
        super().__init__()
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Priority", "Title", "Detail", "Targets"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.btn_refresh = QPushButton("Refresh Tasks"); self.btn_refresh.clicked.connect(self.refresh)
        layout = QVBoxLayout(); layout.addWidget(self.btn_refresh); layout.addWidget(self.table); self.setLayout(layout)
        self.refresh()

    def refresh(self):
        report = load_report_json(); actions = report.get("actions", [])
        self.table.setRowCount(len(actions))
        for r, a in enumerate(actions):
            self.table.setItem(r, 0, QTableWidgetItem(str(a.get("priority",""))))
            self.table.setItem(r, 1, QTableWidgetItem(a.get("title","")))
            self.table.setItem(r, 2, QTableWidgetItem(a.get("detail","")))
            self.table.setItem(r, 3, QTableWidgetItem(", ".join(a.get("targets", []))))
        self.table.resizeColumnsToContents()
