from PyQt6.QtCore import Qt, QAbstractTableModel, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableView, QLineEdit, QLabel
from nha_bridge import run_scan, run_analyze, load_report_json

COLUMNS = ["IP","MAC","Vendor","Category","Risk","Reasons","Ports","Hostname"]

class DevicesModel(QAbstractTableModel):
    def __init__(self, rows=None): super().__init__(); self.rows = rows or []
    def rowCount(self, parent=None): return len(self.rows)
    def columnCount(self, parent=None): return len(COLUMNS)
    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole: return None
        return COLUMNS[section] if orientation==Qt.Orientation.Horizontal else str(section+1)
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        from PyQt6.QtGui import QColor
        if not index.isValid(): return None
        r = self.rows[index.row()]; c = index.column()
        if role == Qt.ItemDataRole.BackgroundRole:
            # subtle risk-based background
            risk = r.get("risk_score", 0)
            if risk >= 6:
                return QColor(80, 30, 30)  # high → dark red
            elif risk >= 3:
                return QColor(80, 70, 30)  # medium → dark amber
            else:
                return QColor(35, 60, 35)  # low → dark green
        if role == Qt.ItemDataRole.DisplayRole:
            return [r.get("ip",""), r.get("mac",""), r.get("vendor",""), r.get("category",""),
                    r.get("risk_score",0), ",".join(r.get("risk_reasons",[])), ",".join(r.get("ports",[])),
                    r.get("hostname","")][c]
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignVCenter | (Qt.AlignmentFlag.AlignRight if c==4 else Qt.AlignmentFlag.AlignLeft)
        return None
    def setRows(self, rows):
        self.beginResetModel(); self.rows = rows; self.endResetModel()

class DevicesTab(QWidget):
    dataChanged = pyqtSignal(dict)
    def __init__(self):
        super().__init__()
        self.model = DevicesModel([])
        self.table = QTableView(); self.table.setModel(self.model)
        self.table.setSortingEnabled(True); self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)

        self.filter_edit = QLineEdit(); self.filter_edit.setPlaceholderText("Filter (IP, MAC, vendor, category, hostname)...")
        self.filter_edit.textChanged.connect(self.apply_filter)

        self.btn_scan = QPushButton("Run Scan"); self.btn_analyze = QPushButton("Analyze/Refresh")
        self.btn_scan.clicked.connect(self.on_scan); self.btn_analyze.clicked.connect(self.on_analyze)

        top = QHBoxLayout(); top.addWidget(self.btn_scan); top.addWidget(self.btn_analyze); top.addStretch(); top.addWidget(QLabel("Search:")); top.addWidget(self.filter_edit)
        layout = QVBoxLayout(); layout.addLayout(top); layout.addWidget(self.table); self.setLayout(layout)
        self._all_rows = []; self.on_analyze()

    def apply_filter(self):
        q = self.filter_edit.text().strip().lower()
        if not q: self.model.setRows(self._all_rows); return
        def match(r):
            return any(q in (str(r.get(k,""))).lower() for k in ["ip","mac","vendor","category","hostname"]) or q in ",".join(r.get("risk_reasons",[])).lower()
        self.model.setRows([r for r in self._all_rows if match(r)])

    def on_scan(self):
        ok, _ = run_scan()
        if not ok: self.btn_scan.setText("Scan Failed")
        self.on_analyze()

    def on_analyze(self):
        ok, _ = run_analyze()
        if not ok: self.model.setRows([]); return
        report = load_report_json()
        rows = report.get("devices", [])
        self._all_rows = rows; self.apply_filter()
        self.dataChanged.emit(report)
