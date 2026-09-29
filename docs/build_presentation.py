"""Build docs/Fraud_Detection_Agent.pptx: IIT Bhilai project presentation."""

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

OUT = "/Users/neoxdev/Documents/FraudDetectionAiAgent/docs/Fraud_Detection_Agent.pptx"

NAVY = RGBColor(0x14, 0x21, 0x3D)
NAVY_2 = RGBColor(0x22, 0x33, 0x5A)
TEAL = RGBColor(0x1F, 0x7A, 0x74)
TEAL_PALE = RGBColor(0xE2, 0xF1, 0xEF)
AMBER = RGBColor(0xE0, 0x9A, 0x2B)
AMBER_PALE = RGBColor(0xFC, 0xF1, 0xDF)
RED = RGBColor(0xB0, 0x3A, 0x2E)
RED_PALE = RGBColor(0xF8, 0xE5, 0xE2)
INK = RGBColor(0x1B, 0x24, 0x30)
MUTED = RGBColor(0x5E, 0x69, 0x73)
LINE = RGBColor(0xD3, 0xDA, 0xE0)
GREY_PALE = RGBColor(0xF1, 0xF3, 0xF5)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
ICE = RGBColor(0xC9, 0xD6, 0xEA)

HEAD = "Cambria"
BODY = "Calibri"

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]
SW, SH = 13.333, 7.5


# ------------------------------------------------------------------ helpers
def bg(slide, color):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def text(slide, x, y, w, h, runs, size=15, color=INK, font=BODY, bold=False, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, italic=False, spacing_after=0, line_spacing=None):
    """runs: str, or list of paragraphs; a paragraph is str or list of (text, overrides)."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    paras = runs if isinstance(runs, list) else [runs]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(spacing_after)
        if line_spacing:
            p.line_spacing = line_spacing
        parts = para if isinstance(para, list) else [(para, {})]
        for part in parts:
            t, o = (part, {}) if isinstance(part, str) else part
            r = p.add_run()
            r.text = t
            f = r.font
            f.name = o.get("font", font)
            f.size = Pt(o.get("size", size))
            f.bold = o.get("bold", bold)
            f.italic = o.get("italic", italic)
            f.color.rgb = o.get("color", color)
    return tb


def bullets(slide, x, y, w, h, items, size=15, color=INK, gap=6):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(gap)
        pPr = p._p.get_or_add_pPr()
        pPr.set("marL", str(Emu(Inches(0.22))))
        pPr.set("indent", str(-Emu(Inches(0.22))))
        bu = pPr.makeelement(qn("a:buChar"), {"char": "•"})
        pPr.append(bu)
        parts = item if isinstance(item, list) else [(item, {})]
        for part in parts:
            t, o = (part, {}) if isinstance(part, str) else part
            r = p.add_run()
            r.text = t
            r.font.name = BODY
            r.font.size = Pt(o.get("size", size))
            r.font.bold = o.get("bold", False)
            r.font.color.rgb = o.get("color", color)
    return tb


def box(slide, x, y, w, h, fill, line=None, radius=True, shadow=False):
    shp = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE,
        Inches(x), Inches(y), Inches(w), Inches(h))
    if radius:
        shp.adjustments[0] = 0.08
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = Pt(1)
    if not shadow:
        shp.shadow.inherit = False
    shp.text_frame.text = ""
    return shp


def node(slide, x, y, w, h, title, sub=None, fill=GREY_PALE, edge=LINE, title_color=INK,
         sub_color=MUTED, tsize=14, ssize=11):
    box(slide, x, y, w, h, fill, edge)
    lines = [[(title, {"bold": True, "size": tsize, "color": title_color})]]
    if sub:
        lines.append([(sub, {"size": ssize, "color": sub_color})])
    text(slide, x + 0.1, y + 0.05, w - 0.2, h - 0.1, lines, align=PP_ALIGN.CENTER,
         anchor=MSO_ANCHOR.MIDDLE, spacing_after=2)


def arrow(slide, x1, y1, x2, y2, color=MUTED, width=1.5, dash=False):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = color
    c.line.width = Pt(width)
    ln = c.line._get_or_add_ln()
    tail = ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"})
    ln.append(tail)
    if dash:
        prst = ln.makeelement(qn("a:prstDash"), {"val": "dash"})
        ln.insert(1, prst)
    return c


def chip(slide, x, y, label, fill=TEAL, color=WHITE, w=None, size=11):
    w = w or (0.16 + 0.085 * len(label))
    s = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(0.3))
    s.adjustments[0] = 0.5
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    s.line.fill.background()
    s.shadow.inherit = False
    tf = s.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = label
    r.font.name = BODY
    r.font.size = Pt(size)
    r.font.bold = True
    r.font.color.rgb = color
    return s


def title(slide, t, kicker=None, dark=False):
    if kicker:
        chip(slide, 0.6, 0.45, kicker, fill=TEAL if not dark else AMBER, color=WHITE if not dark else NAVY)
    text(slide, 0.6, 0.85, 12.1, 0.8, t, size=34, font=HEAD, bold=True, color=WHITE if dark else NAVY)


def footer(slide, n, dark=False):
    text(slide, 0.6, 7.0, 8, 0.3, "Fraud Detection AI Agent", size=10,
         color=ICE if dark else MUTED)
    text(slide, 11.73, 7.0, 1.0, 0.3, str(n), size=10, color=ICE if dark else MUTED, align=PP_ALIGN.RIGHT)


def table(slide, x, y, w, rows, col_w, size=12, header_fill=NAVY, row_h=0.36):
    shape = slide.shapes.add_table(len(rows), len(rows[0]), Inches(x), Inches(y), Inches(w),
                                   Inches(row_h * len(rows)))
    tbl = shape.table
    tblPr = tbl._tbl.tblPr
    style = tblPr.find(qn("a:tableStyleId"))
    if style is not None:
        style.text = "{5940675A-B579-460E-94D1-54222C63F5DA}"  # No Style, Table Grid
    for i, cw in enumerate(col_w):
        tbl.columns[i].width = Inches(cw)
    for r, row in enumerate(rows):
        tbl.rows[r].height = Inches(row_h)
        for c, val in enumerate(row):
            cell = tbl.cell(r, c)
            cell.margin_left = cell.margin_right = Inches(0.08)
            cell.margin_top = cell.margin_bottom = Inches(0.04)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            cell.fill.fore_color.rgb = header_fill if r == 0 else (WHITE if r % 2 else GREY_PALE)
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.text = ""
            run = p.add_run()
            bold = r == 0 or (isinstance(val, tuple) and val[1])
            run.text = val[0] if isinstance(val, tuple) else str(val)
            run.font.name = BODY
            run.font.size = Pt(size)
            run.font.bold = bold
            run.font.color.rgb = WHITE if r == 0 else INK
    return shape


def notes(slide, t):
    slide.notes_slide.notes_text_frame.text = t


# Slides for the IIT Bhilai project presentation. Appended after the helpers of build_deck.py.

# ================================================================== 1 TITLE
s = prs.slides.add_slide(BLANK)
bg(s, NAVY)
text(s, 0.9, 2.2, 11.5, 1.3, "Fraud Detection AI Agent", size=56, font=HEAD, bold=True, color=WHITE)
text(s, 0.9, 4.1, 11, 0.6, "Anand Kumar Singh", size=28, bold=True, color=AMBER)
text(s, 0.9, 4.75, 11, 0.5, "IIT Bhilai", size=22, color=WHITE)
text(s, 0.9, 5.3, 11, 0.5, "2024–2026", size=20, color=ICE)
notes(s, "Project work: an AI-agent system that detects and investigates insurance fraud.")

# ================================================================== 2 OVERVIEW
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
title(s, "Project overview", "OVERVIEW")
text(s, 0.6, 1.85, 6.4, 1.2, [
    [("Problem. ", {"bold": True, "color": NAVY}),
     ("Insurance fraud happens at every stage: when a policy is sold, when the premium is paid, and when a "
      "claim is made, by customers, agents, or people posing as agents.", {})],
], size=15)
text(s, 0.6, 3.05, 6.4, 1.0, [
    [("Objective. ", {"bold": True, "color": NAVY}),
     ("Find suspected fraud automatically, investigate it, and give a human investigator a clear, "
      "evidence-backed case to decide on.", {})],
], size=15)
text(s, 0.6, 4.1, 6.4, 0.4, "Approach: each technique does what it is best at", size=15, bold=True, color=NAVY)
steps = [("Rules", "catch the certain cases", TEAL_PALE, TEAL),
         ("ML model", "scores every claim", TEAL_PALE, TEAL),
         ("AI agents", "investigate and explain", AMBER_PALE, AMBER),
         ("Investigator", "makes the decision", RED_PALE, RED)]
for i, (h, d, f, e) in enumerate(steps):
    x = 0.6 + i * 1.62
    node(s, x, 4.6, 1.45, 1.05, h, d, fill=f, edge=e, tsize=13, ssize=10)
    if i < 3:
        arrow(s, x + 1.46, 5.12, x + 1.61, 5.12, color=NAVY, width=1.5)
text(s, 0.6, 5.9, 6.4, 0.8, "Built on Google Cloud: BigQuery for data, Gemini on Vertex AI for the agents "
     "(Google Agent Development Kit), and Cloud Run for the investigator dashboard.", size=13, color=MUTED)
box(s, 7.5, 1.85, 5.2, 4.85, NAVY)
text(s, 7.8, 2.05, 4.6, 0.4, "At a glance", size=16, bold=True, color=AMBER)
facts = [("4,000", "labelled records in 4 files"), ("17", "fraud types"), ("19", "detection rules"),
         ("778", "alerts raised for investigation"), ("8", "AI agents working as a team"),
         ("100%", "of bad payments caught by rules")]
for i, (n, lab) in enumerate(facts):
    y = 2.6 + i * 0.66
    text(s, 7.8, y, 1.5, 0.55, n, size=24, font=HEAD, bold=True, color=WHITE, anchor=MSO_ANCHOR.MIDDLE)
    text(s, 9.35, y, 3.2, 0.55, lab, size=13, color=ICE, anchor=MSO_ANCHOR.MIDDLE)
footer(s, 2)
notes(s, "The key design idea: cheap, exact methods (rules and a model) screen every record; the AI agents "
         "are only spent on alerts, where their strength (gathering context and explaining) matters; a "
         "person always makes the final decision, and those decisions feed back as new training labels.")

# ================================================================== 3 ARCHITECTURE + DATA
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
title(s, "Architecture and data", "ARCHITECTURE")
layers = [
    ("DATA", "BigQuery", GREY_PALE, ["raw", "clean", "features", "cases"]),
    ("DETECTION", "Python + SQL", TEAL_PALE, ["19 rules", "Claims ML", "Alert queue", "Networks"]),
    ("INVESTIGATION", "Google ADK", AMBER_PALE, ["Orchestrator", "5 specialists", "Case writer", "Reviewer"]),
    ("DECISION", "Cloud Run", RED_PALE, ["Dashboard", "Investigator", "Feedback", ""]),
]
for i, (lab, sub, fill, items) in enumerate(layers):
    y = 1.85 + i * 1.22
    box(s, 0.6, y, 7.7, 1.07, fill, radius=False)
    text(s, 0.75, y + 0.2, 1.65, 0.3, lab, size=12, bold=True, color=NAVY)
    text(s, 0.75, y + 0.55, 1.65, 0.3, sub, size=10, color=MUTED)
    for j, it in enumerate(items):
        if it:
            node(s, 2.45 + j * 1.45, y + 0.2, 1.33, 0.67, it, None, fill=WHITE, edge=NAVY, tsize=11)
    if i < 3:
        arrow(s, 4.45, y + 1.07, 4.45, y + 1.22, color=NAVY, width=2)
text(s, 0.6, 6.78, 7.7, 0.25, "Data flows down; investigator decisions flow back up as new labels.",
     size=10, italic=True, color=MUTED)
files = [
    ("policies_free_insurance.csv", "15.5% fraud", "Policies: cover obtained without really paying: fake "
     "policies, backdating, fronting, free-look abuse."),
    ("claims.csv", "18.4% fraud", "Claims: duplicate, staged, faked-document, inflated or suspiciously early claims."),
    ("payments_bad_payments.csv", "14.4% fraud", "Premium payments that never reached the insurer: refunds, "
     "fake receipts, bounced cheques, agent diversion."),
    ("ghost_broking.csv", "28.5% fraud", "Agent sales: fake or cloned agents, expired or no license, "
     "agents pocketing premiums."),
]
for i, (name, rate, desc) in enumerate(files):
    y = 1.85 + i * 1.22
    box(s, 8.6, y, 4.1, 1.07, GREY_PALE)
    text(s, 8.78, y + 0.1, 2.75, 0.3, name, size=11, bold=True, color=NAVY)
    text(s, 11.35, y + 0.1, 1.2, 0.3, rate, size=11, bold=True, color=RED, align=PP_ALIGN.RIGHT)
    text(s, 8.78, y + 0.42, 3.8, 0.62, desc, size=10, color=INK)
text(s, 8.6, 6.78, 4.1, 0.25, "1,000 labelled records each; linked by policy, customer and agent IDs.",
     size=10, italic=True, color=MUTED)
footer(s, 3)
notes(s, "Four layers, one data store. Every layer reads from and writes to BigQuery, so any stage can be "
         "re-run on its own. The four CSV files are synthetic, set in the Indian insurance market (rupees, "
         "Indian states, UPI and NEFT payments). Each has fraud_flag and fraud_type labels, which are used "
         "for training and testing only and are hidden from the AI agents and the dashboard.")

# ================================================================== 4 FRAUD TYPES
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
title(s, "17 fraud types across the four files", "WHAT COUNTS AS FRAUD")
groups = [
    ("Policies", [("Fake Policy - No Premium Collected", 45), ("Backdated Policy Issuance", 41),
                  ("Fronting / Straw Policyholder", 39), ("Free-Look Period Abuse", 30)]),
    ("Claims", [("Multiple/Duplicate Claims", 52), ("Staged Accident", 39), ("Fake Supporting Documents", 34),
                ("Exaggerated Claim Amount", 33), ("Early Claim Fraud", 26)]),
    ("Payments", [("Duplicate/Unauthorized Refund", 44), ("Fake Payment Receipt", 36),
                  ("Bounced Cheque Used for Coverage", 35), ("Premium Diversion by Agent", 29)]),
    ("Ghost broking", [("Fake/Cloned Agent Identity", 81), ("Premium Pocketing", 80),
                       ("Expired License Sales", 70), ("Unlicensed Selling", 54)]),
]
cw = 2.9
for i, (g, items) in enumerate(groups):
    x = 0.6 + i * (cw + 0.17)
    chip(s, x, 1.95, g.upper(), fill=NAVY, w=cw)
    for j, (name, n) in enumerate(items):
        y = 2.45 + j * 0.78
        box(s, x, y, cw, 0.68, GREY_PALE)
        text(s, x + 0.15, y, 2.05, 0.68, name, size=12, color=INK, anchor=MSO_ANCHOR.MIDDLE)
        text(s, x + 2.15, y, 0.6, 0.68, str(n), size=18, font=HEAD, bold=True, color=TEAL,
             align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)
text(s, 0.6, 6.45, 12.1, 0.4,
     "Counts are the number of labelled fraud records of each type.", size=11, color=MUTED)
footer(s, 4)
notes(s, "Ghost broking is selling insurance without the right to: fake identities, expired or suspended "
         "licenses, or no license. Fronting means the named policyholder is a front for someone else. "
         "The free-look period is the legal window (15 days here) in which a new policy can be cancelled.")

# ================================================================== 5 FINDINGS
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
title(s, "What the data analysis found", "ANALYSIS")
finds = [
    ("One column gives it away", "Backdated flag, duplicate receipt, altered documents, bounced payment: "
     "each is 100% fraud. Easy for rules, but real data is never this clean.", TEAL, TEAL_PALE),
    ("Some columns leak the answer", "claim_status and approved_amount are outcomes of an investigation. "
     "Using them would be cheating, so every rule, model and tool excludes them.", RED, RED_PALE),
    ("Some fraud leaves no trace", "Staged accidents, duplicate claims and fronting look like honest records: "
     "51% of honest claims also have a related claim within 180 days.", AMBER, AMBER_PALE),
    ("Data-quality problems", "92 claims dated in the future; 603 “Valid” licenses already expired; "
     "50 agents with conflicting statuses. Flagged, never deleted.", NAVY, GREY_PALE),
]
for i, (h, body, edge, fill) in enumerate(finds):
    col, row = i % 2, i // 2
    x, y = 0.6 + col * 6.15, 1.95 + row * 2.3
    box(s, x, y, 5.9, 2.05, fill)
    text(s, x + 0.3, y + 0.25, 5.3, 0.5, h, size=19, font=HEAD, bold=True, color=edge)
    text(s, x + 0.3, y + 0.85, 5.3, 1.1, body, size=13, color=INK)
footer(s, 5)
notes(s, "These four findings shaped the design. Automated tests enforce that label and outcome columns are "
         "never used. Because the data is synthetic, the pipeline carries over to real data but the exact "
         "accuracy numbers will not.")

# ================================================================== 6 TECH STACK
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
title(s, "Technology stack", "TOOLS")
rows = [
    ["Layer", "Choice", "Why"],
    [("Language", True), "Python 3.12 with uv", "Standard for data and ML; Google Cloud libraries support it"],
    [("Data", True), "Google BigQuery (Mumbai)", "Managed and shared by every service; access control; data stays in India"],
    [("Rules", True), "YAML file + generated SQL", "Rules change without code changes and run inside BigQuery"],
    [("ML", True), "scikit-learn gradient boosting", "Strong on tabular data"],
    [("Agents", True), "Google ADK 2.9 + Gemini 3.8 Flash", "Tools are plain Python functions; structured, validated output"],
    [("Console", True), "React + TypeScript, FastAPI", "A responsive investigator interface; one service serves both"],
    [("Deployment", True), "Cloud Run, private access", "Scales to zero; only authorised accounts can open it"],
    [("Quality", True), "pytest, 37 tests", "Guard against label leakage, schema drift and broken wiring"],
]
table(s, 0.6, 1.95, 12.1, rows, [1.7, 3.9, 6.5], size=13, row_h=0.5)
footer(s, 6)
notes(s, "BigQuery was chosen over a local database (DuckDB) because the agents and dashboard are deployed on "
         "Google Cloud, and several services and users need to share the data safely.")

# ================================================================== 7 DATA PIPELINE
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
title(s, "Phase 1: loading and cleaning the data", "PHASE 1")
steps = [("CSV files", "4 files", GREY_PALE, LINE), ("fraud_raw", "dates as text", TEAL_PALE, TEAL),
         ("fraud_clean", "typed, dq_* flags", TEAL_PALE, TEAL),
         ("fraud_features", "rules, scores, alerts", TEAL_PALE, TEAL),
         ("fraud_cases", "cases, decisions", AMBER_PALE, AMBER)]
for i, (n, d, f, e) in enumerate(steps):
    x = 0.6 + i * 2.5
    node(s, x, 2.0, 2.15, 1.1, n, d, fill=f, edge=e, tsize=15, ssize=11)
    if i < 4:
        arrow(s, x + 2.17, 2.55, x + 2.48, 2.55, color=NAVY, width=2)
bullets(s, 0.6, 3.6, 7.4, 3.0, [
    [("Explicit schema for every file; ", {"bold": True}), ("a malformed row fails the load instead of being skipped.", {})],
    [("Cleaning in SQL: ", {"bold": True}), ("real dates, empty values made consistent.", {})],
    [("Data-quality flags, never deletions: ", {"bold": True}), ("future dates, expired “Valid” licenses, conflicting agents.", {})],
    [("Row counts checked ", {"bold": True}), ("across CSV, raw and clean tables: 1,000 each.", {})],
], size=14, gap=8)
box(s, 8.4, 3.6, 4.3, 2.9, NAVY)
text(s, 8.7, 3.8, 3.8, 0.4, "Verified in BigQuery", size=16, bold=True, color=AMBER)
text(s, 8.7, 4.3, 3.8, 2.1, [
    [("184 / 144 / 155 / 285", {"bold": True, "color": WHITE}), (" fraud rows", {"color": ICE})],
    [("92", {"bold": True, "color": WHITE}), (" future-dated claims", {"color": ICE})],
    [("603", {"bold": True, "color": WHITE}), (" expired “Valid” licenses", {"color": ICE})],
    [("50", {"bold": True, "color": WHITE}), (" agents with conflicting status", {"color": ICE})],
    [("438", {"bold": True, "color": WHITE}), (" agent sales with no policy", {"color": ICE})],
], size=14, spacing_after=5)
footer(s, 7)
notes(s, "Four BigQuery datasets, one per processing stage. The loader is safe to re-run, and every number "
         "matched the original CSV analysis exactly.")

# ================================================================== 8 RULES
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
title(s, "Phase 1: a rules engine with measured severity", "RULES")
cd = CategoryChartData()
cd.categories = ["Payments", "Policies", "Ghost broking", "Claims"]
cd.add_series("Critical rules only", (100, 55.5, 28.1, 29.3))
cd.add_series("High and critical", (100, 74.8, 95.4, 29.3))
cd.add_series("All rules", (100, 93.5, 95.4, 82.6))
gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.6), Inches(1.9), Inches(7.4), Inches(4.8), cd)
ch = gf.chart
ch.has_title = True
ch.chart_title.text_frame.text = "Recall: share of all fraud caught (%)"
tp = ch.chart_title.text_frame.paragraphs[0]
tp.runs[0].font.size = Pt(14)
tp.runs[0].font.bold = True
tp.runs[0].font.color.rgb = NAVY
tp.runs[0].font.name = BODY
ch.has_legend = True
ch.legend.position = XL_LEGEND_POSITION.BOTTOM
ch.legend.include_in_layout = False
ch.legend.font.size = Pt(11)
ch.legend.font.color.rgb = MUTED
for ser, col in zip(ch.series, [NAVY, TEAL, AMBER]):
    ser.format.fill.solid()
    ser.format.fill.fore_color.rgb = col
plot = ch.plots[0]
plot.gap_width = 60
plot.has_data_labels = True
plot.data_labels.font.size = Pt(10)
plot.data_labels.font.color.rgb = INK
plot.data_labels.number_format = '0'
plot.data_labels.number_format_is_linked = False
plot.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
va = ch.value_axis
va.maximum_scale = 110
va.has_major_gridlines = True
va.major_gridlines.format.line.color.rgb = LINE
va.tick_labels.font.size = Pt(10)
va.tick_labels.font.color.rgb = MUTED
va.format.line.fill.background()
ca = ch.category_axis
ca.tick_labels.font.size = Pt(12)
ca.tick_labels.font.color.rgb = INK
ca.format.line.color.rgb = LINE
text(s, 8.4, 1.95, 4.3, 0.4, "Severity comes from precision", size=16, bold=True, color=NAVY)
table(s, 8.4, 2.45, 4.3, [
    ["Severity", "Precision", "Rules"],
    [("critical", True), "≥ 95%", "11"],
    [("high", True), "≥ 60%", "4"],
    [("medium", True), "≥ 25%", "4"],
], [1.5, 1.4, 1.4], size=12, row_h=0.42)
text(s, 8.4, 4.35, 4.3, 2.3, [
    [("Payments and agent sales are essentially solved by rules. ", {"bold": True}),
     ("Claims are the weak spot: certain rules catch only 29.3%.", {})],
    "",
    [("Safeguard: ", {"bold": True, "color": RED}), ("the engine refuses any rule that uses a label or outcome column.", {})],
], size=13)
footer(s, 8)
notes(s, "Precision is the share of flagged records that are really fraud; recall is the share of all fraud "
         "that gets flagged. Critical rules have 100% precision in every file. A candidate rule was dropped "
         "because its precision (21.5%) was barely above the 18% base rate.")

# ================================================================== 9 CLAIMS MODEL
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
title(s, "Phase 2: a machine learning model for claims", "CLAIMS MODEL")
cd = CategoryChartData()
cd.categories = ["Fake documents", "Exaggerated amount", "Early claim", "Staged accident", "Duplicate claims"]
cd.add_series("Recall at 82% precision", (100, 69.7, 11.5, 7.7, 3.8))
gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(5.3), Inches(1.9), Inches(7.4), Inches(4.5), cd)
ch = gf.chart
ch.has_title = True
ch.chart_title.text_frame.text = "Share of each claim fraud type caught (%), rules + model"
tp = ch.chart_title.text_frame.paragraphs[0]
tp.runs[0].font.size = Pt(14)
tp.runs[0].font.bold = True
tp.runs[0].font.color.rgb = NAVY
tp.runs[0].font.name = BODY
ch.has_legend = False
ser = ch.series[0]
ser.format.fill.solid()
ser.format.fill.fore_color.rgb = TEAL
for idx in (2, 3, 4):
    pt = ser.points[idx]
    pt.format.fill.solid()
    pt.format.fill.fore_color.rgb = RED
plot = ch.plots[0]
plot.gap_width = 45
plot.has_data_labels = True
plot.data_labels.font.size = Pt(11)
plot.data_labels.number_format = '0'
plot.data_labels.number_format_is_linked = False
plot.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
ca = ch.category_axis
ca.reverse_order = True
ca.tick_labels.font.size = Pt(12)
ca.format.line.color.rgb = LINE
va = ch.value_axis
va.maximum_scale = 115
va.minimum_scale = 0
va.has_major_gridlines = True
va.major_gridlines.format.line.color.rgb = LINE
va.tick_labels.font.size = Pt(10)
va.tick_labels.font.color.rgb = MUTED
va.format.line.fill.background()
for i, (n, lab) in enumerate([("29% → 35%", "recall at over 80% precision"),
                              ("0.571", "PR-AUC (rules 0.511, random 0.184)")]):
    y = 1.95 + i * 1.35
    text(s, 0.6, y, 4.5, 0.7, n, size=32, font=HEAD, bold=True, color=TEAL)
    text(s, 0.6, y + 0.7, 4.5, 0.4, lab, size=12, color=MUTED)
bullets(s, 0.6, 4.75, 4.4, 2.0, [
    "Gradient-boosted trees on 29 features from all four files.",
    "Tested on agents it never saw, so it can't memorise them.",
    "Red bars: fraud that leaves no trace in the data.",
], size=13, gap=6)
footer(s, 9)
notes(s, "Cross-validated in five groups by agent. Top features: altered documents, claim-to-sum-insured "
         "ratio, days from policy start to incident, agent complaints and license problems. The model adds "
         "a little; no model can find fraud that leaves no trace in the data.")

# ================================================================== 10 AGENT TEAM
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
title(s, "Phase 3: a team of AI agents", "AI AGENTS")
node(s, 4.9, 1.9, 3.5, 0.9, "Orchestrator", "routes each alert, adds context", fill=AMBER_PALE, edge=AMBER, tsize=15)
specs = [("Claims agent", "duplicate, staged, fake, inflated, early claims"),
         ("Policy agent", "fake, backdated, fronting, free-look"),
         ("Payment agent", "refunds, fake receipts, bounced, diverted"),
         ("Ghost-broking agent", "fake or unlicensed agents, pocketing"),
         ("Network agent", "fraud rings around agents and customers")]
for i, (n, d) in enumerate(specs):
    x = 0.6 + i * 2.47
    node(s, x, 3.3, 2.25, 1.15, n, d, fill=WHITE, edge=AMBER, tsize=13, ssize=10)
    arrow(s, 6.65, 2.82, x + 1.12, 3.28, color=MUTED, width=1)
text(s, 0.6, 4.75, 12.1, 0.4, "What every specialist has in common", size=15, bold=True, color=NAVY)
bullets(s, 0.6, 5.2, 6.0, 1.6, [
    "Read-only BigQuery tools; parameterised queries.",
    "Tools report base rates, so a common pattern isn't mistaken for evidence.",
    "Labels and outcome columns are never returned.",
], size=13, gap=5)
bullets(s, 6.9, 5.2, 5.8, 1.6, [
    "Findings in a fixed, validated format.",
    "Each can only name its own file's fraud types.",
    "Every fact must cite a record ID and exact values.",
], size=13, gap=5)
footer(s, 10)
notes(s, "Built with Google's Agent Development Kit on Gemini 3.8 Flash. Specialists are exposed to the "
         "orchestrator as tools. The network agent is called when the alert's agent or customer is a "
         "network hub.")

# ================================================================== 11 PIPELINE + REVIEWER
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
title(s, "From alert to reviewed case", "INVESTIGATION PIPELINE")
flow = [("Alert queue", "778 alerts by priority", TEAL_PALE, TEAL),
        ("Orchestrator", "+ specialists", AMBER_PALE, AMBER),
        ("Case writer", "only facts from the notes", AMBER_PALE, AMBER),
        ("Reviewer", "re-checks every fact", AMBER_PALE, AMBER),
        ("Investigator", "confirm or dismiss", RED_PALE, RED)]
for i, (n, d, f, e) in enumerate(flow):
    x = 0.6 + i * 2.5
    node(s, x, 1.95, 2.15, 1.05, n, d, fill=f, edge=e, tsize=15, ssize=11)
    if i < 4:
        arrow(s, x + 2.17, 2.47, x + 2.48, 2.47, color=NAVY, width=2)
text(s, 0.6, 3.35, 7.0, 3.4, [
    [("Alerts: ", {"bold": True, "color": NAVY}),
     ("a high or critical rule hit, or a claims model score ≥ 0.42. 608 of the 778 are real fraud.", {})],
    [("Case writer: ", {"bold": True, "color": NAVY}),
     ("evidence with record IDs, people involved, open questions, next steps.", {})],
    [("Reviewer: ", {"bold": True, "color": NAVY}),
     ("never sees the notes. Checks every cited ID exists, re-queries each fact, and corrects the risk, "
      "action or fraud types.", {})],
    [("Honest evaluation: ", {"bold": True, "color": NAVY}),
     ("labels are hidden from the agents and used only to score them.", {})],
], size=14, spacing_after=10)
box(s, 8.0, 3.35, 4.7, 3.35, NAVY)
text(s, 8.3, 3.55, 4.1, 0.4, "Live results", size=16, bold=True, color=AMBER)
stats = [("72", "facts checked by the reviewer"), ("71", "verified; 1 unverifiable, 0 wrong"),
         ("8 / 8", "top alerts: correct fraud type"), ("4 / 5", "specialist test alerts correct")]
for i, (n, lab) in enumerate(stats):
    y = 4.05 + i * 0.64
    text(s, 8.3, y, 1.3, 0.55, n, size=22, font=HEAD, bold=True, color=WHITE, anchor=MSO_ANCHOR.MIDDLE)
    text(s, 9.65, y, 2.9, 0.55, lab, size=12, color=ICE, anchor=MSO_ANCHOR.MIDDLE)
footer(s, 11)
notes(s, "The reviewer checked 72 facts across 11 reviewed cases: 71 verified, 1 unverifiable because a tool "
         "did not return model scores (since fixed), and none contradicted. It made real corrections, such as "
         "removing fraud types that described the agent rather than the record. The one miss among five "
         "harder alerts was a policy cancelled in the free-look window that was labelled honest; the agents "
         "rated it high and recommended a hold, not a rejection.")

# ================================================================== 12 NETWORK
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
title(s, "Network analysis finds what screening missed", "NETWORKS")
cd = CategoryChartData()
cd.categories = ["Hub agents", "Other agents"]
cd.add_series("Fraud rate of unflagged records (%)", (12.3, 2.8))
gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.6), Inches(1.9), Inches(5.6), Inches(4.7), cd)
ch = gf.chart
ch.has_title = True
ch.chart_title.text_frame.text = "Fraud rate among records nothing flagged (%)"
tp = ch.chart_title.text_frame.paragraphs[0]
tp.runs[0].font.size = Pt(14)
tp.runs[0].font.bold = True
tp.runs[0].font.color.rgb = NAVY
tp.runs[0].font.name = BODY
ch.has_legend = False
ser = ch.series[0]
ser.format.fill.solid()
ser.format.fill.fore_color.rgb = MUTED
pt = ser.points[0]
pt.format.fill.solid()
pt.format.fill.fore_color.rgb = RED
plot = ch.plots[0]
plot.gap_width = 80
plot.has_data_labels = True
plot.data_labels.font.size = Pt(14)
plot.data_labels.font.bold = True
plot.data_labels.number_format = '0.0'
plot.data_labels.number_format_is_linked = False
plot.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
va = ch.value_axis
va.maximum_scale = 15
va.minimum_scale = 0
va.has_major_gridlines = True
va.major_gridlines.format.line.color.rgb = LINE
va.tick_labels.font.size = Pt(10)
va.tick_labels.font.color.rgb = MUTED
va.format.line.fill.background()
ca = ch.category_axis
ca.tick_labels.font.size = Pt(13)
ca.format.line.color.rgb = LINE
text(s, 6.7, 1.95, 6.0, 0.5, "A hub: an agent or customer tied to 5+ alerts across 2+ files",
     size=15, bold=True, color=NAVY)
bullets(s, 6.7, 2.55, 6.0, 3.0, [
    [("51 hub agents ", {"bold": True}), ("account for 644 of the 778 alerts.", {})],
    [("Their unflagged records are fraud 12.3% of the time, ", {"bold": True}),
     ("about 4 times the 2.8% for other agents: 91 fraud records the rules and model missed.", {})],
    [("The network agent ", {"bold": True}),
     ("examines a hub's links and suggests up to 10 unflagged records for review.", {})],
    [("Built from alerts only, ", {"bold": True}), ("never from labels.", {})],
], size=14, gap=8)
footer(s, 12)
notes(s, "The entity risk table scores every agent and customer by their links to alerts. The labels were "
         "used only afterwards, to measure how much fraud sits among the unflagged records of hub agents.")

# ================================================================== 13 DASHBOARD + DEPLOYMENT
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
title(s, "Investigator dashboard on Cloud Run", "DELIVERY")
cards = [
    ("Alert queue", "All 778 alerts by priority, with status: open, case ready or decided. Filters by file, "
     "severity and network hubs.", TEAL_PALE, TEAL),
    ("Case view", "Risk after review, cited evidence with the reviewer's check of each fact, next steps, "
     "people involved and network context.", AMBER_PALE, AMBER),
    ("Decisions", "Confirm fraud, not fraud or needs more information. Saved to BigQuery as new labels "
     "for retraining.", RED_PALE, RED),
]
for i, (h, body, fill, edge) in enumerate(cards):
    x = 0.6 + i * 4.1
    box(s, x, 1.95, 3.8, 2.3, fill)
    text(s, x + 0.25, 2.15, 3.3, 0.45, h, size=18, font=HEAD, bold=True, color=edge)
    text(s, x + 0.25, 2.7, 3.3, 1.5, body, size=13, color=INK)
text(s, 0.6, 4.6, 12.1, 0.4, "Deployment", size=16, bold=True, color=NAVY)
bullets(s, 0.6, 5.05, 6.0, 1.8, [
    "Cloud Run in Mumbai; scales to zero when idle.",
    "Private: anonymous visitors are refused (HTTP 403).",
    "“Investigate now” runs the full agent pipeline on demand.",
], size=13, gap=5)
bullets(s, 6.9, 5.05, 5.8, 1.8, [
    "Least-privilege service accounts for running, building and access.",
    "Can read cleaned data; writes only cases and decisions.",
    "Never shows labels to investigators.",
], size=13, gap=5)
footer(s, 13)
notes(s, "The console is a React app served by FastAPI. Access goes through a dedicated invoker service account, because "
         "Cloud Run does not accept identity tokens from personal gcloud logins in this setup.")

# ================================================================== 14 CONCLUSION
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
title(s, "Conclusions and future work", "CONCLUSION")
cols = [
    ("What worked", TEAL, TEAL_PALE, [
        "Rules catch 95–100% of payment and agent-sale fraud with no false alarms.",
        "Agents write cited, reviewable cases; 71 of 72 checked facts verified.",
        "Network analysis surfaces fraud the screening missed (12.3% vs 2.8%).",
    ]),
    ("Limitations", RED, RED_PALE, [
        "Synthetic data: accuracy numbers will not transfer to real data.",
        "Staged, duplicate and fronting fraud leave no trace in these files.",
        "Low default Vertex AI quota limits batch runs.",
    ]),
    ("Future work", NAVY, GREY_PALE, [
        "Real data with repair-shop, hospital and document signals.",
        "Retrain from investigator decisions.",
        "Daily batch runs and a held-out test of the full pipeline.",
    ]),
]
for i, (h, c, fill, items) in enumerate(cols):
    x = 0.6 + i * 4.1
    box(s, x, 1.95, 3.8, 4.7, fill)
    text(s, x + 0.25, 2.15, 3.3, 0.5, h, size=20, font=HEAD, bold=True, color=c)
    bullets(s, x + 0.25, 2.8, 3.35, 3.7, items, size=13, gap=8)
footer(s, 14)
notes(s, "The main lesson: use each technique for what it does best, measure honestly against hidden labels, "
         "and keep a person in charge of the decision.")

# ================================================================== 15 THANK YOU
s = prs.slides.add_slide(BLANK)
bg(s, NAVY)
text(s, 0.9, 2.6, 11.5, 1.2, "Thank you", size=54, font=HEAD, bold=True, color=WHITE)
text(s, 0.9, 3.9, 11.5, 0.6, "Questions?", size=26, color=AMBER)
text(s, 0.9, 5.3, 11.5, 0.5, "Anand Kumar Singh  ·  IIT Bhilai  ·  2024–2026", size=16, color=ICE)
notes(s, "Thank the audience and invite questions.")

prs.save(OUT)
print(OUT)
