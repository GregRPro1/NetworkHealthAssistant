from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtWidgets import QApplication

DARK_QSS = """
QToolBar { background: #2b2d30; border-bottom: 1px solid #3c3f41; spacing: 6px; }
QMenuBar { background: #2b2d30; color: #dddddd; }
QMenuBar::item:selected { background: #3a3d41; }
QMenu { background: #2b2d30; color: #dddddd; border: 1px solid #3c3f41; }
QMenu::item:selected { background: #3a3d41; }
QStatusBar { background: #2b2d30; border-top: 1px solid #3c3f41; }
QStatusBar QLabel { color: #dddddd; }
QTableView { gridline-color: #3c3f41; }
QHeaderView::section { background: #2f3236; color: #dddddd; padding: 4px; border: 0px; border-right: 1px solid #3c3f41; }
"""

def _apply_dark_palette(app: QApplication):
    app.setStyle("Fusion")
    pal = QPalette()
    c_bg = QColor(30, 32, 34)
    c_panel = QColor(45, 47, 50)
    c_text = QColor(220, 220, 220)
    c_disabled = QColor(127, 127, 127)
    c_highlight = QColor(42, 130, 218)

    pal.setColor(QPalette.ColorRole.Window, c_bg)
    pal.setColor(QPalette.ColorRole.WindowText, c_text)
    pal.setColor(QPalette.ColorRole.Base, QColor(25, 27, 29))
    pal.setColor(QPalette.ColorRole.AlternateBase, c_panel)
    pal.setColor(QPalette.ColorRole.ToolTipBase, c_panel)
    pal.setColor(QPalette.ColorRole.ToolTipText, c_text)
    pal.setColor(QPalette.ColorRole.Text, c_text)
    pal.setColor(QPalette.ColorRole.Button, c_panel)
    pal.setColor(QPalette.ColorRole.ButtonText, c_text)
    pal.setColor(QPalette.ColorRole.Highlight, c_highlight)
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, c_disabled)
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, c_disabled)
    app.setPalette(pal)
    app.setStyleSheet(DARK_QSS)

def _apply_light_palette(app: QApplication):
    app.setStyle("Fusion")
    app.setPalette(app.style().standardPalette())
    app.setStyleSheet("")

def apply_theme(app: QApplication, mode: str = "dark"):
    if (mode or "").lower() == "light":
        _apply_light_palette(app)
    else:
        _apply_dark_palette(app)

# Backwards-compat
def apply_dark_theme(app: QApplication):
    apply_theme(app, "dark")
