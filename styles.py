from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtWidgets import QApplication

def apply_dark_theme(app: QApplication):
    app.setStyle("Fusion")
    palette = QPalette()
    c_bg = QColor(30, 32, 34)
    c_panel = QColor(45, 47, 50)
    c_text = QColor(220, 220, 220)
    c_disabled = QColor(127, 127, 127)
    c_highlight = QColor(42, 130, 218)

    palette.setColor(QPalette.ColorRole.Window, c_bg)
    palette.setColor(QPalette.ColorRole.WindowText, c_text)
    palette.setColor(QPalette.ColorRole.Base, QColor(25, 27, 29))
    palette.setColor(QPalette.ColorRole.AlternateBase, c_panel)
    palette.setColor(QPalette.ColorRole.ToolTipBase, c_panel)
    palette.setColor(QPalette.ColorRole.ToolTipText, c_text)
    palette.setColor(QPalette.ColorRole.Text, c_text)
    palette.setColor(QPalette.ColorRole.Button, c_panel)
    palette.setColor(QPalette.ColorRole.ButtonText, c_text)
    palette.setColor(QPalette.ColorRole.Highlight, c_highlight)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, c_disabled)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, c_disabled)
    app.setPalette(palette)


# --- extra qss ---
QToolBar { background: #2b2d30; border-bottom: 1px solid #3c3f41; spacing: 6px; }
QMenuBar { background: #2b2d30; color: #ddd; }
QMenuBar::item:selected { background: #3a3d41; }
QMenu { background: #2b2d30; color: #ddd; border: 1px solid #3c3f41; }
QMenu::item:selected { background: #3a3d41; }

QStatusBar { background: #2b2d30; border-top: 1px solid #3c3f41; }
QStatusBar QLabel { color: #ddd; }

QTableView { gridline-color: #3c3f41; }
QHeaderView::section { background: #2f3236; color: #ddd; padding: 4px; border: 0px; border-right: 1px solid #3c3f41; }
