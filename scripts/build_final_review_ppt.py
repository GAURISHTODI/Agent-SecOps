"""Build the final-review deck from the VIT Review-3 template.

    python scripts/build_final_figures.py      # diagrams used below
    python scripts/build_final_review_ppt.py

Demo-oriented, 19 slides. The template is edited in place so the VIT
branding, slide master, footers and the SDG / TRL pictures stay as shipped.
New slides: where the agent sits, the flowchart and four live-demo slides
built from dashboard screenshots in docs/screenshots/final/. Slide 3 keeps a
clearly marked placeholder for the guide's real approval e-mail.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pptx import Presentation  # noqa: E402
from pptx.chart.data import CategoryChartData  # noqa: E402
from pptx.dml.color import RGBColor  # noqa: E402
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION  # noqa: E402
from pptx.enum.shapes import MSO_SHAPE  # noqa: E402
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN  # noqa: E402
from pptx.util import Emu, Pt  # noqa: E402

from scripts.build_final_ppt import (  # noqa: E402
    add_pic, fill, fit, place, set_para, shape_named, strip_highlight, textbox,
)

TEMPLATE = ROOT / "Review 3- 28-10- 2026.pptx"
OUTPUT = ROOT / "Agent SecOps - Final Review Presentation.pptx"
FIG = ROOT / "docs" / "figures"
SHOT = ROOT / "docs" / "screenshots"
FINAL = SHOT / "final"
EMU = 914400

HEAD_FILL = RGBColor(0x4F, 0x81, 0xBD)
ROW_FILL = RGBColor(0xE9, 0xEE, 0xF6)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
INK = RGBColor(0x20, 0x20, 0x20)
MUTED = RGBColor(0x59, 0x59, 0x59)
BLUE = RGBColor(0x2A, 0x78, 0xD6)
ORANGE = RGBColor(0xEB, 0x68, 0x34)


def inch(v):
    return int(v * EMU)


def set_title(slide, text):
    """Replace a template title's text, keeping its run formatting."""
    runs = slide.shapes.title.text_frame.paragraphs[0].runs
    runs[0].text = text
    for r in runs[1:]:
        r.text = ""


def new_slide(prs, footer_source, title):
    """A slide carrying the template's title style, date, footer and number.

    The title is a copy of the template's own title shape (30 pt bold Times
    New Roman at a fixed position), so new slides match the template ones.
    """
    s = prs.slides.add_slide(prs.slide_layouts[1])
    for ph in list(s.placeholders):
        ph._element.getparent().remove(ph._element)
    s.shapes._spTree.append(copy.deepcopy(footer_source.shapes.title._element))
    for ph in footer_source.placeholders:
        if ph.placeholder_format.idx in (10, 11, 12):
            s.shapes._spTree.append(copy.deepcopy(ph._element))
    set_title(s, title)
    return s


def picture(slide, path, left, top, box_w, box_h):
    w, h = fit(path, inch(box_w), inch(box_h))
    pic = add_pic(slide, path, inch(left), inch(top), w, h)
    pic.line.color.rgb = RGBColor(0xBF, 0xBF, 0xBF)
    pic.line.width = Pt(0.75)
    return w / EMU, h / EMU


def caption(slide, left, top, width, text, size=12, bold=True, color=INK):
    tb = textbox(slide, inch(left), inch(top), inch(width), inch(0.4), [text], size, bold, color)
    tb.text_frame.margin_left = tb.text_frame.margin_right = 0
    return tb


def bullets(slide, left, top, width, height, lines, size=14):
    tb = textbox(slide, inch(left), inch(top), inch(width), inch(height), lines, size)
    for p in tb.text_frame.paragraphs:
        p.space_after = Pt(6)
    return tb


def table(slide, rows, head, left, top, width, height, widths, size=11, head_size=12):
    gf = slide.shapes.add_table(len(rows) + 1, len(head), inch(left), inch(top), inch(width), inch(height))
    tbl = gf.table
    for ci, w in enumerate(widths):
        tbl.columns[ci].width = inch(w)
    for ci, h in enumerate(head):
        c = tbl.cell(0, ci)
        c.text = h
        c.fill.solid()
        c.fill.fore_color.rgb = HEAD_FILL
        for r in c.text_frame.paragraphs[0].runs:
            r.font.size = Pt(head_size)
            r.font.bold = True
            r.font.color.rgb = WHITE
    for ri, row in enumerate(rows, 1):
        for ci, val in enumerate(row):
            c = tbl.cell(ri, ci)
            c.text = val
            c.fill.solid()
            c.fill.fore_color.rgb = ROW_FILL if ri % 2 else WHITE
            c.margin_top = c.margin_bottom = Pt(3)
            for para in c.text_frame.paragraphs:
                for r in para.runs:
                    r.font.size = Pt(size)
                    r.font.color.rgb = INK
    return tbl


def notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


# ----------------------------------------------------------------------
def main() -> int:
    prs = Presentation(str(TEMPLATE))
    S = list(prs.slides)
    footer = S[10]

    # ---- title -----------------------------------------------------------
    title = shape_named(S[0], "Title 6")
    runs = title.text_frame.paragraphs[0].runs
    runs[0].text = "B.Tech. Computer Science and Engineering (Information Security)"
    for r in runs[1:5]:
        r.text = ""
    runs[5].text = "  BCSE497J – Project-I"
    runs[6].text = ""
    runs[7].text = "SecOps Agent for CAF/WAF compliant Cloud Deployments in CI/CD"
    team = shape_named(S[0], "object 3").text_frame.paragraphs
    third = copy.deepcopy(team[3]._p)
    team[3]._p.addnext(third)
    from pptx.text.text import _Paragraph
    set_para(_Paragraph(third, team[3]._parent), "Gaurish Todi – 23BCI0262", 20, True)
    set_para(team[2], "Bhumika Singh – 23BCE0196", 20, True)
    set_para(team[3], "Akshat Gupta – 23BCE0958", 20, True)
    set_para(team[6], "Dr. S. M. Farooq, Associate Professor Grade-1, SCOPE", 20, True)
    strip_highlight(S[0])
    notes(S[0], "Introduce the team and the one-line idea: a compliance gate that stops bad "
                "cloud infrastructure between terraform plan and terraform apply.")

    # ---- NEW: where the agent sits ---------------------------------------
    where = new_slide(prs, footer, "Where Agent SecOps Sits")
    w, h = fit(FIG / "final_where_agent_sits.png", inch(12.2), inch(5.3))
    add_pic(where, FIG / "final_where_agent_sits.png", (inch(13.333) - w) // 2, inch(1.45), w, h)
    notes(where, "Every existing check acts either on source code one file at a time (Checkov, "
                 "tfsec) or after the resource already exists and bills (Azure Policy, Defender). "
                 "Our agent judges the exact planned change, after plan and before apply, so a "
                 "BLOCK means nothing is ever created.")

    # ---- approval mail (must be the real mail) ---------------------------
    s = S[1]
    fill(shape_named(s, "Content Placeholder 2").text_frame, [
        "Approval mail from Dr. S. M. Farooq: screenshot to be pasted below.",
        "It must show: PowerPoint approved, project demonstration approved, final report "
        "satisfied, Turnitin plagiarism % and Turnitin AI score (each 25% or less).",
    ], 18)
    for pic in [x for x in s.shapes if x.shape_type == 13]:
        pic._element.getparent().remove(pic._element)
    strip_highlight(s)
    ph = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(1780053), Emu(3300000), Emu(8942979), Emu(2300000))
    ph.fill.background()
    ph.line.color.rgb = RGBColor(0xA0, 0xA0, 0xA0)
    ph.line.width = Pt(1.5)
    ph.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    ph.text_frame.text = "[ Paste the guide's real approval e-mail here ]"
    ph.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    for r in ph.text_frame.paragraphs[0].runs:
        r.font.size = Pt(24)
        r.font.bold = True
        r.font.color.rgb = RGBColor(0xA0, 0xA0, 0xA0)

    # ---- aim -------------------------------------------------------------
    fill(shape_named(S[2], "Content Placeholder 2").text_frame, [
        "To build an agent that sits between terraform plan and terraform apply and stops "
        "cloud deployments that break CAF and WAF guidance, before any resource exists or "
        "costs anything.",
        "Catch risk that only appears when resources are combined, not just one at a time.",
        "Return pass, remediate or block with a plain-language report and a ready fix, the "
        "same way for Azure, AWS and GCP, cheaply enough to run on every pull request.",
    ], 22)

    # ---- abstract --------------------------------------------------------
    fill(shape_named(S[3], "Content Placeholder 2").text_frame, [
        "Scanners such as Checkov and tfsec enforce only rules someone has written, one "
        "resource at a time; CAF and WAF are mostly narrative guidance.",
        "Our agent reads the Terraform plan and decides in layers: Step 0 reads the plan, "
        "Layer 1 runs 22 deterministic rules, Layer 2a applies 12 organisational customized "
        "policies from a CAF/WAF knowledge base, Layer 2b scores dependency-graph risk, and "
        "Layer 3 applies thresholds and waivers.",
        "42 seeded violations: rules alone 33 (78.6%), with reasoning 42 (100%), "
        "0 verdict-affecting false positives, on hand-written and real terraform plans alike.",
        "Four graph scenarios where every resource is low risk alone but HIGH together; "
        "146 automated tests; runs in GitHub Actions in front of a live Azure deployment.",
    ], 18)

    # ---- literature review -------------------------------------------------
    s = S[4]
    for shp in list(s.shapes):
        if shp.shape_type == 13 or type(shp).__name__ == "PlaceholderPicture":
            shp._element.getparent().remove(shp._element)
    rows = [
        ("Rahman et al., ICSE 2019", "Security smells in IaC", "Analysis of Puppet scripts",
         "+ real smells\n− one language", "7 smells; hard-coded secrets common"),
        ("Saavedra & Ferreira, ASE 2022 (GLITCH)", "Smell detection across IaC tools",
         "Shared intermediate model", "+ polyglot\n− rules only", "One model can serve many tools"),
        ("Chiari et al., ICSA-C 2022", "Survey of IaC static analysis", "Literature survey",
         "+ broad\n− builds nothing", "Mostly rule-based, one resource at a time"),
        ("Malul et al., 2024 (GenKubeSec)", "LLM for Kubernetes misconfiguration",
         "Prompted model detects and explains", "+ reasons about intent\n− K8s only, unverified",
         "Models can explain and fix"),
        ("Lewis et al., NeurIPS 2020 (RAG)", "Ground a model in retrieved knowledge",
         "Retrieve, then generate", "+ less guessing\n− needs a good index", "Retrieval improves answers"),
        ("Pearce et al., IEEE S&P 2022", "Is AI-written code secure?", "Probe Copilot on risky tasks",
         "+ shows the risk\n− code generation only", "Verify model output before trusting it"),
        ("Ou, Govindavajhala & Appel, USENIX Security 2005 (MulVAL)", "Find multi-step attack paths",
         "Logic rules over configuration and vulnerabilities", "+ chains across hosts\n− needs a full vulnerability model",
         "Small issues combine into real attack paths"),
        ("Poolsappasit, Dewri & Ray, IEEE TDSC 2012", "Quantify risk along attack paths",
         "Bayesian attack graph", "+ a risk number per asset\n− needs calibrated probabilities",
         "An asset's risk depends on what can reach it"),
    ]
    table(s, rows, ("Paper", "Objective", "Methodology", "Pros / Cons", "Findings"),
          0.45, 1.6, 12.4, 5.15, (2.75, 2.3, 2.45, 2.55, 2.35), size=10.5, head_size=12)
    notes(s, "The last two papers are new since Review 3. MulVAL and Bayesian attack graphs show "
             "that risk lives in combinations and can be scored along paths; Layer 2b applies "
             "that idea to a Terraform plan's dependency graph, before anything is deployed.")

    # ---- research gap ------------------------------------------------------
    fill(shape_named(S[5], "Content Placeholder 2").text_frame, [
        "Rule engines cannot judge guidance nobody has encoded, so much of CAF and WAF is unenforced.",
        "They judge one resource at a time: an open firewall and a weak database are two "
        "separate notes, never one dangerous path.",
        "Work that uses language models rarely says how to keep them from harming a pipeline: "
        "inventing resources, repeating rules, blocking on a guess.",
        "Tools are mostly single-cloud, and post-deployment tools act after the resource "
        "exists and bills.",
    ], 22)

    # ---- objectives --------------------------------------------------------
    body = shape_named(S[6], "Content Placeholder 2")
    place(body, 838200, inch(1.35), 10515600, inch(2.6))
    fill(body.text_frame, [
        "Gate every Terraform plan before apply: pass, remediate or block by exit code.",
        "One rule set across Azure, AWS and GCP through cloud-neutral resource kinds.",
        "Detect combined risk across resources with an explainable graph score.",
        "Keep reasoning bounded and advisory, and measure exactly what it adds.",
    ], 18)
    tb = shape_named(S[6], "TextBox 6")
    tp = tb.text_frame.paragraphs
    if len(tp[0].runs) >= 3:
        tp[0].runs[1].text = "Outcomes: "
        tp[0].runs[2].text = "Product (open-source tool)"
        for r in tp[0].runs[3:]:
            r.text = ""
    for r in tp[1].runs:
        r.text = "\t\t\t\t\t\t\t\tConference paper planned"

    # ---- architecture ------------------------------------------------------
    s = S[7]
    body = shape_named(s, "Content Placeholder 2")
    place(body, inch(8.85), inch(1.5), inch(4.1), inch(5.0))
    fill(body.text_frame, [
        "Runs between plan and apply; the exit code is the decision.",
        "Step 0 reads the plan into cloud-neutral kinds and a dependency graph.",
        "Layers 1, 2a and 2b find problems; only Layer 3 decides.",
        "BLOCK means nothing is ever created.",
    ], 15)
    w, h = fit(FIG / "final_architecture.png", inch(8.2), inch(5.15))
    add_pic(s, FIG / "final_architecture.png", inch(0.45), inch(1.45), w, h)

    # ---- NEW: flowchart ----------------------------------------------------
    flow = new_slide(prs, footer, "Flowchart: How One Plan Is Judged")
    w, h = fit(FIG / "final_flowchart.png", inch(8.9), inch(5.2))
    add_pic(flow, FIG / "final_flowchart.png", inch(0.45), inch(1.45), w, h)
    bullets(flow, 9.6, 1.6, 3.4, 5.0, [
        "Read it as a snake: left to right, back right to left, then left to right.",
        "Invalid input stops with exit 3, never a silent pass.",
        "The reasoning layer can be switched off; the gate still works on rules alone.",
        "Only rule findings can block by default; layer-2 findings warn.",
    ], 14)
    notes(flow, "Walk the three rows: read and Layer 1; the reasoning layer, 2a then 2b; Layer 3's "
                "two decisions. Point out that waivers are applied before the graph, so an "
                "accepted risk is not raised again as exposure on a neighbour.")

    # ---- functional requirements + modules ------------------------------------
    s = S[8]
    set_title(s, "Functional Requirements and Modules")
    body = shape_named(s, "Content Placeholder 2")
    place(body, inch(0.6), inch(1.5), inch(6.2), inch(5.1))
    fill(body.text_frame, [
        "FR1  Read Terraform plan JSON (BOM-safe), including child modules.",
        "FR2  Normalise Azure, AWS and GCP resources; treat replace as create.",
        "FR3  Run rules, organisational policies and graph risk without duplicates.",
        "FR4  Apply thresholds, overrides and expiring waivers.",
        "FR5  Exit 0 / 1 / 2 / 3 for pass / remediate / block / error.",
        "FR6  Markdown, JSON, SARIF and PDF reports with a fix per finding.",
    ], 16)
    table(s, [
        ("Plan parser and dependency graph", "Akshat"),
        ("Layer 1: 22 deterministic rules", "Akshat"),
        ("Layer 2a: organisational customized policies", "Gaurish"),
        ("Layer 2b: dependency-graph risk", "Gaurish"),
        ("Layer 3: thresholds and waivers", "Gaurish"),
        ("CLI, reports, CI/CD and Azure", "Bhumika"),
        ("Dashboard and evaluation harness", "Gaurish"),
    ], ("Module", "Owner"), 7.1, 1.55, 5.75, 4.4, (4.35, 1.4), size=13, head_size=13)

    # ---- NEW: live demo 1 ------------------------------------------------------
    d1 = new_slide(prs, footer, "Live Demo 1: Run the Gate, Watch Every Stage")
    w1, h1 = picture(d1, FINAL / "01_controls_input.png", 0.45, 1.45, 6.15, 3.7)
    caption(d1, 0.45, 1.5 + h1, 6.15, "Pick a plan, or run real terraform on a seeded module")
    w2, h2 = picture(d1, FINAL / "02_pipeline_trace.png", 6.8, 1.45, 6.1, 3.95)
    caption(d1, 6.8, 1.5 + h2, 6.1, "Real timings: terraform about 12 s, the gate itself 25 ms")
    bullets(d1, 0.45, 5.95, 12.4, 0.8, [
        "Pacing replays terraform init, plan, show, then Step 0 and Layers 1, 2a, 2b and 3, one by one.",
    ], 14)
    notes(d1, "Demo: choose 'AWS - tangled dependency graph (mesh)' in Run the real pipeline and "
              "click terraform plan -> gate. With Pacing on, explain each stage as it appears. "
              "Nothing is applied; the module uses dummy credentials.")

    # ---- NEW: live demo 2 ------------------------------------------------------
    d2 = new_slide(prs, footer, "Live Demo 2: Step 0 and Layers 1 + 2a")
    w1, h1 = picture(d2, FINAL / "03_step0_resources.png", 0.45, 1.45, 6.15, 4.3)
    caption(d2, 0.45, 1.5 + h1, 6.15, "Step 0: 22 resources mapped to cloud-neutral kinds")
    w2, h2 = picture(d2, FINAL / "04_layers_findings.png", 6.8, 1.45, 6.1, 4.3)
    caption(d2, 6.8, 1.5 + h2, 6.1, "12 rule findings + 6 from reasoning, each mapped to a pillar")
    bullets(d2, 0.45, 5.95, 12.4, 0.8, [
        "Switch the reasoning layer off and run again: the orange segment disappears.",
    ], 14)
    notes(d2, "Show the resource table (count and for_each instances, the child module) and the "
              "layer split. Toggle the Reasoning layer switch to show what Layer 2 adds.")

    # ---- NEW: live demo 3 ------------------------------------------------------
    d3 = new_slide(prs, footer, "Live Demo 3: Risk That Exists Only in Combination")
    w1, h1 = picture(d3, FINAL / "05_dependency_graph.png", 0.45, 1.45, 5.9, 4.75)
    caption(d3, 0.45, 1.5 + h1, 5.9, "aws_mesh: edge SG -> db SG -> orders DB, risk 0.65 HIGH")
    caption(d3, 6.65, 1.45, 6.2, "Seeded scenarios: low risk alone, high risk together", 15)
    table(d3, [
        ("aws_mesh", "debug rule 0.47 / shared key 0.36", "0.64 HIGH"),
        ("aws_thousand_cuts", "1 public IP: 0.19, not reported", "6 public IPs: 0.66 HIGH"),
        ("aws_shared_trust", "each team's module: nothing", "all three teams: 0.67 HIGH"),
        ("aws_risk_spectrum", "4 hops: 0.00, 3 hops: 0.32", "2 hops: 0.47, 1 hop: 0.63"),
    ], ("Module", "Alone", "Together"), 6.65, 1.95, 6.2, 2.9, (1.9, 2.5, 1.8), size=12, head_size=12)
    bullets(d3, 6.65, 5.05, 6.2, 1.6, [
        "Risk = reachable exposure x weakness x asset value.",
        "Exposure fades x0.75 per hop and stops after 3 hops.",
        "Reported only if the connection itself adds risk.",
    ], 13)
    notes(d3, "Click Simulate exposure spread: sources light up, exposure spreads hop by hop, "
              "then risk scores appear. Then open 'three teams, one shared key': each team's "
              "module passes its own review, yet together the payments database is HIGH.")

    # ---- NEW: live demo 4 ------------------------------------------------------
    d4 = new_slide(prs, footer, "Live Demo 4: Verdict, Reports and CI")
    w1, h1 = picture(d4, FINAL / "06_pdf_report.png", 0.45, 1.45, 4.1, 4.4)
    caption(d4, 0.45, 1.5 + h1, 4.1, "PDF report: verdict, pillar, fix")
    w2, h2 = picture(d4, FINAL / "07_json_report.png", 4.75, 1.45, 2.4, 4.4)
    caption(d4, 4.75, 1.5 + h2, 2.6, "JSON for machines")
    w3, h3 = picture(d4, SHOT / "github_actions_run7.png", 7.4, 1.45, 5.5, 2.8)
    caption(d4, 7.4, 1.5 + h3, 5.5, "GitHub Actions: seeded modules blocked, apply needs approval")
    bullets(d4, 7.4, 2.05 + h3, 5.5, 2.0, [
        "Layer 3 verdict BLOCK: exit code 2 stops terraform apply.",
        "Same result as PR comment, JSON, SARIF (Security tab) and PDF.",
        "OIDC login: no cloud secret is stored in the repository.",
    ], 13)
    notes(d4, "Download the PDF from the dashboard. Optionally run the CLI: "
              "python -m agent.cli evaluate --plan examples/plans/real/azure_noncompliant.plan.json, "
              "then $LASTEXITCODE shows 2.")

    # ---- experiments and results ----------------------------------------------------
    s = S[10]
    body = shape_named(s, "Content Placeholder 2")
    place(body, inch(6.95), inch(1.5), inch(5.95), inch(5.1))
    fill(body.text_frame, [
        "42 seeded violations across Azure, AWS and GCP: rules alone 33 (78.6%), "
        "with reasoning 42 (100%), +9 found only by reasoning.",
        "Identical on real terraform show -json output; 0 verdict-affecting false positives, "
        "and the compliant module passes.",
        "Graph layer: four scenarios, low risk alone, HIGH (0.64 to 0.67) together.",
        "146 automated tests; the gate runs in about 10 to 25 ms.",
        "Limit: we wrote the seeds, so 100% is an upper bound; the LLM reasoner is not yet benchmarked.",
    ], 15)
    cd = CategoryChartData()
    cd.categories = ["Azure (28)", "AWS (8)", "GCP (6)"]
    cd.add_series("Rules only", (21, 7, 5))
    cd.add_series("Rules + reasoning", (28, 8, 6))
    gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, inch(0.45), inch(1.5),
                            inch(6.3), inch(5.0), cd)
    ch = gf.chart
    ch.has_title = True
    ch.chart_title.text_frame.text = "Seeded violations detected"
    ch.chart_title.text_frame.paragraphs[0].runs[0].font.size = Pt(14)
    ch.chart_title.text_frame.paragraphs[0].runs[0].font.bold = True
    ch.has_legend = True
    ch.legend.position = XL_LEGEND_POSITION.BOTTOM
    ch.legend.include_in_layout = False
    ch.legend.font.size = Pt(12)
    for ser, col in zip(ch.plots[0].series, (BLUE, ORANGE)):
        ser.format.fill.solid()
        ser.format.fill.fore_color.rgb = col
    plot = ch.plots[0]
    plot.gap_width = 80
    plot.has_data_labels = True
    plot.data_labels.font.size = Pt(12)
    plot.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    ch.value_axis.has_major_gridlines = True
    ch.value_axis.major_gridlines.format.line.color.rgb = RGBColor(0xE1, 0xE0, 0xD9)
    ch.value_axis.tick_labels.font.size = Pt(11)
    ch.value_axis.tick_labels.font.color.rgb = MUTED
    ch.category_axis.tick_labels.font.size = Pt(12)
    ch.category_axis.tick_labels.font.color.rgb = MUTED
    ch.value_axis.maximum_scale = 30

    # ---- conclusion -------------------------------------------------------------------
    fill(shape_named(S[11], "Content Placeholder 2").text_frame, [
        "A working gate for three clouds: 22 explained rules, 12 organisational customized "
        "policies, dependency-graph risk, thresholds and waivers, and CI that blocks bad plans "
        "in front of a live Azure deployment.",
        "Testing on real terraform output exposed gaps the fixtures hid (nested settings, "
        "module links, values unknown until apply); each is fixed and covered by a test.",
        "Future work: flag values unknown at plan time; benchmark on independent code against "
        "Checkov; benchmark the LLM reasoner; calibrate the graph weights; apply exactly the "
        "gated plan.",
    ], 18)

    # ---- outcome achieved ----------------------------------------------------------------
    fill(shape_named(S[12], "Content Placeholder 2").text_frame, [
        "Patent: none filed.",
        "Conference / journal: paper being prepared (not yet submitted).",
        "Start-up: none.",
        "Product: open-source agent, GitHub Actions workflow, dashboard, seeded test modules "
        "and benchmark (github.com/GAURISHTODI/Agent-SecOps).",
    ], 20)

    # ---- references ------------------------------------------------------------------------
    rect = shape_named(S[13], "Rectangle 3")
    place(rect, inch(0.55), inch(1.65), inch(12.2), inch(5.0))
    fill(rect.text_frame, [
        "[1] A. Rahman, C. Parnin, L. Williams, \"The seven sins: security smells in IaC scripts,\" ICSE, 2019.",
        "[2] N. Saavedra, J. F. Ferreira, \"GLITCH: polyglot security smell detection in IaC,\" ASE, 2022.",
        "[3] M. Chiari, M. De Pascalis, M. Pradella, \"Static analysis of infrastructure as code: a survey,\" ICSA-C, 2022.",
        "[4] E. Malul, Y. Meidan, Y. Mirsky, Y. Elovici, \"GenKubeSec: LLM-based Kubernetes misconfiguration detection,\" arXiv, 2024.",
        "[5] P. Lewis et al., \"Retrieval-augmented generation for knowledge-intensive NLP tasks,\" NeurIPS, 2020.",
        "[6] H. Pearce et al., \"Asleep at the keyboard? Assessing the security of GitHub Copilot's code contributions,\" IEEE S&P, 2022.",
        "[7] X. Ou, S. Govindavajhala, A. W. Appel, \"MulVAL: A logic-based network security analyzer,\" USENIX Security Symposium, 2005.",
        "[8] N. Poolsappasit, R. Dewri, I. Ray, \"Dynamic security risk management using Bayesian attack graphs,\" IEEE TDSC, vol. 9, no. 1, 2012.",
        "[9] Microsoft Learn, Cloud Adoption Framework and Azure Well-Architected Framework, accessed Oct 2026.",
    ], 16)
    rect.text_frame.auto_size = MSO_AUTO_SIZE.NONE
    rect.text_frame.word_wrap = True
    rect.text_frame.vertical_anchor = MSO_ANCHOR.TOP

    # ---- order: drop the separate Modules slide, place the new ones ----------------
    ids = prs.slides._sldIdLst
    entries = {sld.get("id"): sld for sld in ids}

    def entry(slide):
        return next(e for e in ids if e.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
                    == prs.part.relate_to(slide.part, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"))

    order = [S[0], where, S[1], S[2], S[3], S[4], S[5], S[6], S[7], flow, S[8],
             d1, d2, d3, d4, S[10], S[11], S[12], S[13]]
    keep = [entry(sl) for sl in order]
    modules = entry(S[9])
    rid = modules.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
    for e in list(ids):
        ids.remove(e)
    for e in keep:
        ids.append(e)
    prs.part.drop_rel(rid)
    del entries

    prs.save(str(OUTPUT))
    print("saved", OUTPUT.name, "slides:", len(prs.slides))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
