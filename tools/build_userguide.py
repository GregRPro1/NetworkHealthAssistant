from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.colors import HexColor
import datetime, os, io

def build_pdf(out_path="docs/UserGuide.pdf"):
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle('Heading1', parent=styles['Heading1'], textColor=HexColor("#222"))
    h2 = ParagraphStyle('Heading2', parent=styles['Heading2'], textColor=HexColor("#333"))
    body = ParagraphStyle('Body', parent=styles['BodyText'], leading=14, fontSize=10)

    doc = SimpleDocTemplate(out_path, pagesize=A4, leftMargin=18*mm, rightMargin=18*mm, topMargin=18*mm, bottomMargin=18*mm)
    story = []

    # Cover
    story.append(Paragraph("<b>Network Health Assistant</b><br/>User Guide", h1))
    story.append(Spacer(1, 10*mm))
    story.append(Paragraph(f"Version 1.0 — {datetime.date.today().isoformat()}", body))
    story.append(Spacer(1, 60))
    story.append(Paragraph("This guide covers installation, configuration, desktop app usage, the API server, and the iOS companion.", body))
    story.append(PageBreak())

    def add_md(title, path):
        story.append(Paragraph(title, h1))
        story.append(Spacer(1, 4*mm))
        with open(path, "r", encoding="utf-8") as f:
            txt = f.read()
        # naive markdown → paragraphs split
        for para in txt.split("\n\n"):
            story.append(Paragraph(para.replace("\n","<br/>"), body))
            story.append(Spacer(1, 2*mm))

    add_md("Setup", "docs/setup.md")
    story.append(PageBreak())
    add_md("Using the Desktop App", "docs/using.md")
    story.append(PageBreak())
    add_md("iOS App", "docs/ios.md")
    story.append(PageBreak())
    add_md("Security Best Practices", "docs/security.md")
    story.append(PageBreak())
    add_md("Troubleshooting", "docs/troubleshooting.md")

    doc.build(story)
    return out_path

if __name__ == "__main__":
    out = build_pdf()
    print("Wrote", out)
