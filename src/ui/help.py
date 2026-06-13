# src/ui/help.py
from __future__ import annotations
import os
from pathlib import Path
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTextBrowser

class HelpWindow(QDialog):
    def __init__(self, parent=None, doc_md="docs/index.md", doc_pdf="docs/UserGuide.pdf"):
        super().__init__(parent)
        self.setWindowTitle("Help & Documentation")
        self.resize(900, 640)
        lay = QVBoxLayout(self)

        pdf = Path(doc_pdf)
        md  = Path(doc_md)
        self.viewer = QTextBrowser()
        if pdf.exists():
            self.viewer.setHtml(
                f"<h2>User Guide (PDF)</h2>"
                f"<p>The PDF user guide is available here:</p>"
                f"<p><a href='{pdf.resolve().as_uri()}'>Open UserGuide.pdf</a></p>"
            )
        else:
            try:
                text = md.read_text(encoding="utf-8")
                html = text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
                html = html.replace("\n\n", "<br/><br/>").replace("\n","<br/>")
                self.viewer.setHtml(f"<div style='color:#ddd;background:#1e2022;font-family:Segoe UI, sans-serif'>{html}</div>")
            except Exception as e:
                self.viewer.setPlainText(f"Could not load documentation:\n{e}")
        lay.addWidget(self.viewer)

        btns = QHBoxLayout()
        btn_open = QPushButton("Open PDF")
        btn_open.clicked.connect(lambda: os.startfile(str(pdf)) if os.name=="nt" and pdf.exists() else None)
        btn_close = QPushButton("Close"); btn_close.clicked.connect(self.close)
        if pdf.exists(): btns.addWidget(btn_open)
        btns.addStretch(); btns.addWidget(btn_close)
        lay.addLayout(btns)
