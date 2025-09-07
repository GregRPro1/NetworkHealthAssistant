from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
from PyQt6.QtCore import Qt
from nha_bridge import load_report_json
from matplot_embed import MplCanvas

class KpiCard(QFrame):
    def __init__(self, title:str, value:str):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName("kpiCard")
        title_lbl = QLabel(title); title_lbl.setProperty("class","kpiTitle")
        value_lbl = QLabel(value); value_lbl.setProperty("class","kpiValue")
        layout = QVBoxLayout(); layout.addWidget(title_lbl); layout.addWidget(value_lbl); layout.addStretch()
        layout.setContentsMargins(12,8,12,8)
        self.setLayout(layout)

class DashboardTab(QWidget):
    def __init__(self):
        super().__init__()
        self.btn_refresh = QPushButton("Refresh Dashboard")
        self.btn_refresh.clicked.connect(self.refresh)

        # KPI row
        self.kpi_total = KpiCard("Total Devices", "—")
        self.kpi_new   = KpiCard("New Devices", "—")
        self.kpi_high  = KpiCard("High Risk", "—")
        self.kpi_med   = KpiCard("Medium Risk", "—")
        self.kpi_low   = KpiCard("Low Risk", "—")

        kpi_row = QHBoxLayout()
        for w in [self.kpi_total, self.kpi_new, self.kpi_high, self.kpi_med, self.kpi_low]:
            kpi_row.addWidget(w)
        kpi_row.addStretch()

        # Charts
        self.risk_chart = MplCanvas(width=5, height=3, dpi=100)
        self.cat_chart  = MplCanvas(width=5, height=3, dpi=100)

        charts = QHBoxLayout()
        charts.addWidget(self.risk_chart, 1)
        charts.addWidget(self.cat_chart, 1)

        layout = QVBoxLayout()
        layout.addWidget(self.btn_refresh, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addLayout(kpi_row)
        layout.addLayout(charts, 1)
        self.setLayout(layout)

        # Apply simple stylesheet for KPI cards
        self.setStyleSheet("""
        QFrame#kpiCard { border: 1px solid #3c3f41; border-radius: 8px; background: #2b2d30; }
        .kpiTitle { font-size: 11pt; color: #bfc7d5; }
        .kpiValue { font-size: 18pt; font-weight: 600; }
        """)

        self.refresh()

    def refresh(self):
        report = load_report_json()
        s = report.get("summary", {})
        rb = s.get("risk_buckets", {})
        bycat = report.get("summary", {}).get("by_category", {})

        # Update KPIs
        self.kpi_total.layout().itemAt(1).widget().setText(str(s.get("total", 0)))
        self.kpi_new.layout().itemAt(1).widget().setText(str(s.get("new_devices", 0)))
        self.kpi_high.layout().itemAt(1).widget().setText(str(rb.get("high", 0)))
        self.kpi_med.layout().itemAt(1).widget().setText(str(rb.get("medium", 0)))
        self.kpi_low.layout().itemAt(1).widget().setText(str(rb.get("low", 0)))

        # Risk chart (bar)
        self.risk_chart.clear()
        x = ["High","Medium","Low"]
        y = [rb.get("high",0), rb.get("medium",0), rb.get("low",0)]
        self.risk_chart.ax.bar(x, y)  # no explicit colors
        self.risk_chart.ax.set_title("Risk Buckets")
        self.risk_chart.ax.set_ylabel("Count")
        self.risk_chart.draw()

        # Category chart (bar)
        self.cat_chart.clear()
        if bycat:
            x2 = list(bycat.keys())
            y2 = [bycat[k] for k in x2]
            self.cat_chart.ax.bar(x2, y2)  # no explicit colors
            self.cat_chart.ax.set_title("Devices by Category")
            self.cat_chart.ax.set_ylabel("Count")
            self.cat_chart.ax.tick_params(axis='x', labelrotation=20)
        else:
            self.cat_chart.ax.text(0.5,0.5,"No data", ha='center', va='center', transform=self.cat_chart.ax.transAxes)
        self.cat_chart.draw()
