"""Render docs/demo_script.md to docs/Demo_Script.pdf.

Handles the subset of Markdown the script uses: headings, pipe tables, block
quotes (the spoken lines), bullets, horizontal rules, bold and inline code.

    uv run --with reportlab python docs/build_demo_script_pdf.py
"""

import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

DOCS = Path(__file__).resolve().parent
SOURCE = DOCS / "demo_script.md"
OUT = DOCS / "Demo_Script.pdf"

INK = colors.HexColor("#1B2733")
NAVY = colors.HexColor("#1F3A5F")
TEAL = colors.HexColor("#2A7F79")
MUTED = colors.HexColor("#5B6770")
RULE = colors.HexColor("#D5DCE2")
PALE_NAVY = colors.HexColor("#E8EEF5")
PALE_TEAL = colors.HexColor("#E9F3F2")
PALE_GREY = colors.HexColor("#F4F6F8")

ss = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=ss["Normal"], fontName="Helvetica", fontSize=9.8,
                      leading=13.6, textColor=INK, spaceAfter=6)
SAY = ParagraphStyle("say", parent=BODY, fontName="Helvetica", fontSize=11, leading=15.5,
                     textColor=INK, leftIndent=8, spaceAfter=9)
SAY_BULLET = ParagraphStyle("saybullet", parent=SAY, leftIndent=22, bulletIndent=10, spaceAfter=3)
BULLET = ParagraphStyle("bullet", parent=BODY, leftIndent=13, bulletIndent=2, spaceAfter=3)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=8.6, leading=11.4, spaceAfter=0)
CELL_H = ParagraphStyle("cellh", parent=CELL, fontName="Helvetica-Bold", textColor=colors.white)
H1 = ParagraphStyle("h1", parent=BODY, fontName="Helvetica-Bold", fontSize=20, leading=25,
                    textColor=NAVY, spaceBefore=2, spaceAfter=4)
H2 = ParagraphStyle("h2", parent=BODY, fontName="Helvetica-Bold", fontSize=13.5, leading=18,
                    textColor=NAVY, spaceBefore=14, spaceAfter=6)
H3 = ParagraphStyle("h3", parent=BODY, fontName="Helvetica-Bold", fontSize=10.5, leading=14,
                    textColor=TEAL, spaceBefore=9, spaceAfter=3)
SUB = ParagraphStyle("sub", parent=BODY, fontSize=10.5, textColor=TEAL, spaceAfter=10)

WIDTH = 170 * mm


def inline(text: str) -> str:
    """Markdown emphasis and code to reportlab markup, with XML escaped first."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`(.+?)`", r'<font face="Courier" size="9">\1</font>', text)
    return text


def table_flowable(rows: list[list[str]]) -> Table:
    widths = [0.30, 0.55, 0.15] if len(rows[0]) == 3 else [1 / len(rows[0])] * len(rows[0])
    if len(rows[0]) == 2:
        widths = [0.32, 0.68]
    data = [[Paragraph(inline(c), CELL_H if i == 0 else CELL) for c in row]
            for i, row in enumerate(rows)]
    t = Table(data, colWidths=[w * WIDTH for w in widths], repeatRows=1)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for i in range(1, len(rows)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), PALE_GREY))
    t.setStyle(TableStyle(style))
    return t


def quote_flowable(lines: list[str]) -> Table:
    """Join wrapped source lines into paragraphs; keep list items separate."""
    body, buffer = [], []

    def flush_buffer():
        if buffer:
            body.append(Paragraph(inline(" ".join(buffer)), SAY))
            buffer.clear()

    for line in lines:
        if not line.strip():
            flush_buffer()
        elif line.startswith("- "):
            flush_buffer()
            body.append(Paragraph(inline(line[2:]), SAY_BULLET, bulletText="\u2022"))
        else:
            buffer.append(line.strip())
    flush_buffer()
    t = Table([[body]], colWidths=[WIDTH])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE_TEAL),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, TEAL),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def action_flowable(text: str) -> Table:
    t = Table([[Paragraph(inline(text), BODY)]], colWidths=[WIDTH])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE_NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def build() -> None:
    lines = SOURCE.read_text().splitlines()
    story: list = []
    quote: list[str] = []
    table: list[list[str]] = []
    para: list[str] = []
    pending_heading = None

    def add(flowable) -> None:
        """Keep a heading with whatever follows it, so none is orphaned."""
        nonlocal pending_heading
        if pending_heading is not None:
            story.append(KeepTogether([pending_heading, flowable]))
            pending_heading = None
        else:
            story.append(flowable)

    def flush_para() -> None:
        nonlocal para
        if para:
            add(Paragraph(inline(" ".join(para)), BODY))
            para = []

    def flush_blocks() -> None:
        """Close an open quote or table; paragraphs are closed separately."""
        nonlocal quote, table
        if quote:
            add(quote_flowable(quote))
            story.append(Spacer(1, 6))
            quote = []
        if table:
            add(table_flowable(table))
            story.append(Spacer(1, 6))
            table = []

    for raw in lines:
        line = raw.rstrip()
        if line.startswith("> "):
            flush_para()
            quote.append(line[2:])
            continue
        if line == ">":
            quote.append("")
            continue
        if line.startswith("|"):
            flush_para()
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue  # separator row
            table.append(cells)
            continue
        flush_blocks()

        if not line:
            flush_para()
            continue
        if line.startswith(("# ", "## ", "### ", "---", "- ", "**Show:**", "**Open", "**Filter",
                            "**Scroll", "**Before you start**")):
            flush_para()
        if line.startswith("# "):
            story.append(Paragraph(inline(line[2:]), H1))
        elif line.startswith("## "):
            pending_heading = Paragraph(inline(line[3:]), H2)
        elif line.startswith("### "):
            pending_heading = Paragraph(inline(line[4:]), H3)
        elif line.startswith("---"):
            story.append(Spacer(1, 2))
            story.append(HRFlowable(width="100%", thickness=0.6, color=RULE))
            story.append(Spacer(1, 2))
        elif line.startswith("- "):
            add(Paragraph(inline(line[2:]), BULLET, bulletText="•"))
        elif line.startswith("**Show:**") or line.startswith("**Open") or line.startswith("**Filter") \
                or line.startswith("**Scroll") or line.startswith("**Before you start**"):
            add(action_flowable(line))
            story.append(Spacer(1, 4))
        elif line.startswith("Anand Kumar Singh"):
            story.append(Paragraph(inline(line), SUB))
        else:
            para.append(line)
    flush_para()
    flush_blocks()
    if pending_heading is not None:
        story.append(pending_heading)
    if pending_heading is not None:
        story.append(pending_heading)

    def page(canvas, doc):
        canvas.saveState()
        if doc.page > 1:
            canvas.setStrokeColor(RULE)
            canvas.setLineWidth(0.5)
            canvas.line(20 * mm, 285 * mm, 190 * mm, 285 * mm)
            canvas.setFont("Helvetica", 7.5)
            canvas.setFillColor(MUTED)
            canvas.drawString(20 * mm, 287 * mm, "Fraud Detection AI Agent — demo script")
            canvas.drawRightString(190 * mm, 287 * mm, "Anand Kumar Singh")
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawCentredString(105 * mm, 10 * mm, str(doc.page))
        canvas.restoreState()

    doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=16 * mm,
                            title="Fraud Detection AI Agent — demo script",
                            author="Anand Kumar Singh")
    doc.build(story, onFirstPage=page, onLaterPages=page)
    print(OUT)


if __name__ == "__main__":
    build()
