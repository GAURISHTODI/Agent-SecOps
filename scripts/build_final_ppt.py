"""Fill the Review-3 presentation template (VIT) for the final review.

    python scripts/build_final_ppt.py

The supplied template is edited in place so VIT branding, the slide master,
footers and the SDG / TRL pictures stay exactly as shipped. Two extra slides
(live dashboard, CI/CD and Azure evidence) are inserted after "Experiments
and Results". Slide 2 needs the guide's real approval e-mail, which this
script deliberately does not invent: it leaves a clearly marked placeholder.
"""
from __future__ import annotations

import copy
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "Review 3- 28-10- 2026.pptx"
OUTPUT = ROOT / "Agent SecOps - Review 3 Presentation.pptx"
FIG = ROOT / "docs" / "figures"
SHOT = ROOT / "docs" / "screenshots"
CROP = SHOT / "report"


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def clear_extra(tf, keep: int = 1):
    for p in list(tf.paragraphs)[keep:]:
        p._p.getparent().remove(p._p)


def set_para(p, text, size=None, bold=None, color=None):
    runs = p.runs
    if runs:
        runs[0].text = text
        for r in runs[1:]:
            r._r.getparent().remove(r._r)
        r = runs[0]
    else:
        r = p.add_run()
        r.text = text
    r.font.highlight_color = None if hasattr(r.font, "highlight_color") else None
    if size:
        r.font.size = Pt(size)
    if bold is not None:
        r.font.bold = bold
    if color is not None:
        r.font.color.rgb = color
    return p


def fill(tf, lines, size=None, bold_first=False):
    """Replace the text of a text frame, cloning the first paragraph for each extra line."""
    paras = list(tf.paragraphs)
    proto = copy.deepcopy(paras[0]._p)
    for p in paras[1:]:
        p._p.getparent().remove(p._p)
    set_para(tf.paragraphs[0], lines[0], size)
    last = tf.paragraphs[0]._p
    for line in lines[1:]:
        new = copy.deepcopy(proto)
        last.addnext(new)
        last = new
    for para, line in zip(tf.paragraphs, lines):
        set_para(para, line, size)


def strip_highlight(slide):
    """The template marks its instructions with a yellow highlight; remove it."""
    ns = "{http://schemas.openxmlformats.org/drawingml/2006/main}highlight"
    for el in list(slide._element.iter(ns)):
        el.getparent().remove(el)


def place(shape, left, top, width, height):
    """Set all four geometry values (setting one alone breaks inherited placeholders)."""
    shape.left, shape.top, shape.width, shape.height = (
        Emu(int(left)), Emu(int(top)), Emu(int(width)), Emu(int(height)))


def shape_named(slide, name):
    return next(s for s in slide.shapes if s.name == name)


def add_pic(slide, path, left, top, width=None, height=None):
    return slide.shapes.add_picture(str(path), Emu(left), Emu(top),
                                    Emu(width) if width else None,
                                    Emu(height) if height else None)


def fit(path, box_w, box_h):
    with Image.open(path) as im:
        w, h = im.size
    scale = min(box_w / w, box_h / h)
    return int(w * scale), int(h * scale)


def textbox(slide, left, top, width, height, lines, size=14, bold=False, color=None):
    tb = slide.shapes.add_textbox(Emu(left), Emu(top), Emu(width), Emu(height))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        r = p.add_run()
        r.text = line
        r.font.size = Pt(size)
        r.font.bold = bold
        if color is not None:
            r.font.color.rgb = color
    return tb


def reorder(prs, old_index, new_index):
    ids = prs.slides._sldIdLst
    el = list(ids)[old_index]
    ids.remove(el)
    ids.insert(new_index, el)


# ----------------------------------------------------------------------
def main() -> int:
    prs = Presentation(str(TEMPLATE))
    S = list(prs.slides)
    EMU = 914400

    # ---- 1. title ------------------------------------------------------
    title = shape_named(S[0], "Title 6")
    p = title.text_frame.paragraphs[0]
    runs = p.runs
    runs[0].text = "B.Tech. Computer Science and Engineering (Information Security)"
    for r in runs[1:5]:
        r.text = ""
    runs[5].text = "  BCSE497J – Project-I"
    runs[6].text = ""
    runs[7].text = "SecOps Agent for CAFWAF compliant Cloud Deployments in CICD"
    for r in p.runs:
        r.font.highlight_color = None
    team = shape_named(S[0], "object 3").text_frame.paragraphs
    # three members: clone the second member line for the third
    third = copy.deepcopy(team[3]._p)
    team[3]._p.addnext(third)
    from pptx.text.text import _Paragraph
    set_para(_Paragraph(third, team[3]._parent), "Gaurish Todi – 23BCI0262", 20, True)
    set_para(team[2], "Bhumika Singh – 23BCE0196", 20, True)
    set_para(team[3], "Akshat Gupta – 23BCE0958", 20, True)
    set_para(team[6], "Dr. S. M. Farooq, Associate Professor Grade-1, SCOPE", 20, True)
    strip_highlight(S[0])

    # ---- 2. approval mail (must be the real mail) ----------------------
    s = S[1]
    body = shape_named(s, "Content Placeholder 2")
    fill(body.text_frame, [
        "Approval mail from Dr. S. M. Farooq: screenshot to be pasted below.",
        "It must show: PowerPoint approved, project demonstration approved, final report "
        "satisfied, Turnitin plagiarism % and Turnitin AI score (each 25% or less).",
    ], 18)
    for pic in [x for x in s.shapes if x.shape_type == 13]:
        pic._element.getparent().remove(pic._element)
    strip_highlight(s)
    box = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(1780053), Emu(3300000),
                             Emu(8942979), Emu(2300000))
    box.fill.background()
    box.line.color.rgb = RGBColor(0xA0, 0xA0, 0xA0)
    box.line.width = Pt(1.5)
    tf = box.text_frame
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.text = "[ Paste the guide's real approval e-mail here ]"
    tf.paragraphs[0].alignment = PP_ALIGN.CENTER
    for r in tf.paragraphs[0].runs:
        r.font.size = Pt(24)
        r.font.bold = True
        r.font.color.rgb = RGBColor(0xA0, 0xA0, 0xA0)

    # ---- 3. aim ----------------------------------------------------------
    fill(shape_named(S[2], "Content Placeholder 2").text_frame, [
        "To build an agent that sits between terraform plan and terraform apply and stops "
        "cloud deployments that break CAF and WAF guidance, before any resource exists "
        "or costs anything.",
        "Return pass, remediate or block with a plain-language report and a ready fix.",
        "Work the same way for Azure, AWS and GCP, and stay cheap enough to run on every pull request.",
    ], 22)

    # ---- 4. abstract -----------------------------------------------------
    fill(shape_named(S[3], "Content Placeholder 2").text_frame, [
        "Scanners such as Checkov and tfsec only enforce rules someone has already written; "
        "CAF and WAF are mostly narrative guidance.",
        "Our agent reads the Terraform plan as JSON, maps resources to cloud-neutral kinds, "
        "and decides through three layers: 22 deterministic rules, a verified reasoning "
        "layer, and an organisational policy layer.",
        "42 seeded violations: rules alone found 37, rules plus reasoning found 42, "
        "with 0 false positives on the compliant module.",
        "Works on real plans for Azure, AWS and GCP, runs in GitHub Actions, protects a "
        "live Azure deployment costing about ₹4 a month.",
    ], 20)

    # ---- 5. literature review (table) ------------------------------------
    s = S[4]
    for shp in list(s.shapes):
        # the template ships a picture of an empty table and a picture of a note
        if shp.shape_type == 13 or type(shp).__name__ == "PlaceholderPicture":
            shp._element.getparent().remove(shp._element)
    rows = [
        ("Rahman et al., ICSE 2019", "Find security smells in IaC", "Analysis of Puppet scripts",
         "+ real smells  − one language", "7 smells; hard-coded secrets common"),
        ("Saavedra & Ferreira, ASE 2022 (GLITCH)", "Smell detection across IaC tools",
         "Shared intermediate model", "+ polyglot  − rules only", "One model can serve many tools"),
        ("Chiari et al., ICSA-C 2022", "Survey of IaC static analysis", "Literature survey",
         "+ broad  − builds nothing", "Mostly rule-based, one resource at a time"),
        ("Malul et al., 2024 (GenKubeSec)", "LLM for Kubernetes misconfiguration",
         "Prompted model detects and explains", "+ reasons about intent  − K8s only, unverified",
         "Models can explain and fix"),
        ("Lewis et al., NeurIPS 2020 (RAG)", "Ground a model in retrieved knowledge",
         "Retrieve, then generate", "+ less guessing  − needs a good index", "Retrieval improves answers"),
        ("Pearce et al., IEEE S&P 2022", "Is AI-written code secure?", "Probe Copilot on risky tasks",
         "+ shows the risk  − code generation only", "Verify model output before trusting it"),
    ]
    head = ("Paper", "Objective", "Methodology", "Pros / Cons", "Findings")
    gf = s.shapes.add_table(len(rows) + 1, 5, Emu(int(0.45 * EMU)), Emu(int(1.4 * EMU)),
                            Emu(int(12.4 * EMU)), Emu(int(4.6 * EMU)))
    tbl = gf.table
    for ci, w in enumerate((2.6, 2.4, 2.3, 2.7, 2.4)):
        tbl.columns[ci].width = Emu(int(w * EMU))
    for ci, h in enumerate(head):
        c = tbl.cell(0, ci)
        c.text = h
        c.fill.solid()
        c.fill.fore_color.rgb = RGBColor(0x4F, 0x81, 0xBD)
        for r in c.text_frame.paragraphs[0].runs:
            r.font.size = Pt(13)
            r.font.bold = True
            r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    for ri, row in enumerate(rows, 1):
        for ci, val in enumerate(row):
            c = tbl.cell(ri, ci)
            c.text = val.replace("  −", "\n−")
            c.fill.solid()
            c.fill.fore_color.rgb = (RGBColor(0xE9, 0xEE, 0xF6) if ri % 2
                                     else RGBColor(0xFF, 0xFF, 0xFF))
            for para in c.text_frame.paragraphs:
                for r in para.runs:
                    r.font.size = Pt(12)
                    r.font.color.rgb = RGBColor(0x20, 0x20, 0x20)

    # ---- 6. research gap -------------------------------------------------
    fill(shape_named(S[5], "Content Placeholder 2").text_frame, [
        "Rule engines cannot judge guidance nobody has encoded, so much of CAF and WAF is unenforced.",
        "Work that uses language models rarely says how to keep them from harming a pipeline: "
        "inventing resources, repeating rules, blocking on a guess.",
        "Most tools look at one cloud, so multi-cloud teams maintain several rule sets.",
        "Post-deployment tools (Azure Policy, Defender) act after the resource exists and bills.",
    ], 22)

    # ---- 7. objectives ---------------------------------------------------
    body = shape_named(S[6], "Content Placeholder 2")
    place(body, 838200, int(1.35 * EMU), 10515600, int(2.6 * EMU))
    fill(body.text_frame, [
        "Gate every Terraform plan before apply: pass, remediate or block by exit code.",
        "One rule set across Azure, AWS and GCP through canonical resource kinds.",
        "Reasoning layer for unencoded intent that is bounded, verified and advisory by default.",
        "Measure what reasoning adds; prove it on a live Azure deployment on a tiny budget.",
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

    # ---- 8. architecture ---------------------------------------------------
    s = S[7]
    body = shape_named(s, "Content Placeholder 2")
    place(body, 8.7 * EMU, 1.5 * EMU, 4.2 * EMU, 4.8 * EMU)
    fill(body.text_frame, [
        "Runs between plan and apply; exit code is the decision.",
        "Layer 0 normalises to canonical kinds.",
        "Layer 1: 22 rules. Layer 2: verified reasoning. Layer 3: policy and waivers.",
        "Block means nothing is ever created.",
    ], 15)
    w, h = fit(FIG / "fig2_architecture.png", int(8.0 * EMU), int(4.9 * EMU))
    add_pic(s, FIG / "fig2_architecture.png", int(0.5 * EMU), int(1.5 * EMU), w, h)

    # ---- 9. functional requirements ------------------------------------------
    fill(shape_named(S[8], "Content Placeholder 2").text_frame, [
        "FR1  Read Terraform plan JSON (including BOM-prefixed files).",
        "FR2  Normalise Azure, AWS and GCP resources; treat replace as create.",
        "FR3  Evaluate all rules, then the optional reasoning layer without duplicates.",
        "FR4  Apply policy: thresholds, overrides, expiring waivers.",
        "FR5  Exit 0 / 1 / 2 / 3 for pass / remediate / block / error.",
        "FR6  Markdown, JSON and SARIF reports with a fix per finding; dashboard with PDF export.",
    ], 20)

    # ---- 10. modules -----------------------------------------------------------
    fill(shape_named(S[9], "Content Placeholder 2").text_frame, [
        "Parser and canonical model: plan JSON to cloud-neutral resources (Akshat)",
        "Rule engine: 22 rules, each with a pillar and rationale (Akshat)",
        "Reasoning layer: retrieve, deduplicate, judge, verify, govern (Gaurish)",
        "Policy: thresholds, overrides, waivers that expire (Gaurish)",
        "CLI and reports: Markdown, JSON, SARIF, exit codes (Bhumika)",
        "CI/CD and Azure: Actions workflow, OIDC, Terraform modules (Bhumika)",
        "Dashboard and evaluation harness (Gaurish)",
    ], 18)

    # ---- 11. experiments and results ----------------------------------------------
    s = S[10]
    body = shape_named(s, "Content Placeholder 2")
    place(body, 0.6 * EMU, 1.5 * EMU, 5.2 * EMU, 4.8 * EMU)
    fill(body.text_frame, [
        "42 seeded violations across three clouds.",
        "Rules alone: 37 (88.1%). With reasoning: 42 (100%). Recovered: 5. False positives: 0.",
        "69 automated tests, all passing.",
        "Real terraform plans: AWS 21 findings, GCP 14, Azure 47, all blocked.",
        "Honest limit: labels written by us, so 100% is a regression result, not independent accuracy.",
    ], 16)
    w, h = fit(FIG / "fig8_benchmark.png", int(6.6 * EMU), int(4.6 * EMU))
    add_pic(s, FIG / "fig8_benchmark.png", int(6.0 * EMU), int(1.6 * EMU), w, h)

    # ---- extra slide A: live dashboard -----------------------------------------------
    layout = prs.slide_layouts[1]
    a = prs.slides.add_slide(layout)
    # copy footer / date / slide-number placeholders from slide 11 so the slide matches
    for ph in list(a.placeholders):
        if ph.placeholder_format.idx != 0:
            ph._element.getparent().remove(ph._element)
    for ph in S[10].placeholders:
        if ph.placeholder_format.idx in (10, 11, 12):
            a.shapes._spTree.append(copy.deepcopy(ph._element))
    _title(a, "Live Demonstration: Dashboard (same engine as the CLI)")
    imgs = [CROP / "team_top.png", CROP / "off.png", CROP / "tf.png"]
    labels = ["Three clouds, one gate: BLOCK, 14 findings", "Reasoning layer off: orange segment disappears",
              "Real terraform plan to gate, in one click"]
    x = int(0.45 * EMU)
    for img, lab in zip(imgs, labels):
        w, h = fit(img, int(4.1 * EMU), int(4.6 * EMU))
        add_pic(a, img, x, int(1.55 * EMU), w, h)
        textbox(a, x, int(1.55 * EMU) + h + 40000, int(4.1 * EMU), 400000, [lab], 12, True)
        x += int(4.25 * EMU)

    # ---- extra slide B: CI/CD and Azure ------------------------------------------------
    b = prs.slides.add_slide(layout)
    for ph in list(b.placeholders):
        if ph.placeholder_format.idx != 0:
            ph._element.getparent().remove(ph._element)
    for ph in S[10].placeholders:
        if ph.placeholder_format.idx in (10, 11, 12):
            b.shapes._spTree.append(copy.deepcopy(ph._element))
    _title(b, "Live Demonstration: GitHub Actions and Azure")
    runp = SHOT / "github_actions_run7.png"
    apprp = SHOT / "github_approve_dialog.png"
    azp = SHOT / "azure_resource_groups.png"
    w, h = fit(runp, int(6.4 * EMU), int(2.9 * EMU))
    add_pic(b, runp, int(0.45 * EMU), int(1.5 * EMU), w, h)
    textbox(b, int(0.45 * EMU), int(1.5 * EMU) + h + 20000, int(6.4 * EMU), 330000,
            ["Run 7: unit tests and four gate jobs passed; apply awaits approval"], 12, True)
    w3, h3 = fit(azp, int(6.4 * EMU), int(1.9 * EMU))
    add_pic(b, azp, int(0.45 * EMU), int(1.5 * EMU) + h + 420000, w3, h3)
    w2, h2 = fit(apprp, int(4.6 * EMU), int(2.0 * EMU))
    add_pic(b, apprp, int(7.3 * EMU), int(1.5 * EMU), w2, h2)
    textbox(b, int(7.3 * EMU), int(1.5 * EMU) + h2 + 20000, int(5.4 * EMU), 330000,
            ["Human approval before production"], 12, True)
    textbox(b, int(7.3 * EMU), int(4.1 * EMU), int(5.5 * EMU), 2200000, [
        "Runs 1 to 6 failed: Azure login rejected the repository's ID-based OIDC subject.",
        "Fix: added federated credentials for that subject; no secret is stored.",
        "Footprint: 2 resource groups, 2 storage accounts, 1 capped workspace, about ₹4 a month.",
    ], 13)
    reorder(prs, len(prs.slides) - 2, 11)
    reorder(prs, len(prs.slides) - 1, 12)

    # ---- conclusion (slide 12 in template, now 14) ---------------------------------------
    s = S[11]
    fill(shape_named(s, "Content Placeholder 2").text_frame, [
        "A working gate: real plans for three clouds, 22 explained rules, a verified reasoning "
        "layer, policy, and CI that blocks bad plans and protects a live deployment.",
        "Running things for real found faults fixtures hid; auditing against Microsoft's "
        "documentation corrected seven of our own claims.",
        "Future work: benchmark the LLM reasoner on independent repositories with Checkov as "
        "baseline; AWS and GCP native knowledge bases; Bicep and Pulumi; a conference paper.",
    ], 18)

    # ---- outcome achieved --------------------------------------------------------------------
    s = S[12]
    body = shape_named(s, "Content Placeholder 2")
    fill(body.text_frame, [
        "Patent: none filed.",
        "Conference / journal: paper being prepared (not yet submitted). Core result planned: "
        "independent evaluation of the LLM reasoner.",
        "Start-up: none.",
        "Product: open-source agent, GitHub Actions workflow, dashboard and documented knowledge "
        "audit (github.com/GAURISHTODI/Agent-SecOps).",
    ], 20)

    # ---- references -----------------------------------------------------------------------------
    s = S[13]
    rect = shape_named(s, "Rectangle 3")
    place(rect, 0.55 * EMU, 1.4 * EMU, 12.2 * EMU, 4.9 * EMU)
    fill(rect.text_frame, [
        "[1] A. Rahman, C. Parnin, L. Williams, \"The seven sins: security smells in IaC scripts,\" ICSE, 2019.",
        "[2] N. Saavedra, J. F. Ferreira, \"GLITCH: polyglot security smell detection in IaC,\" ASE, 2022.",
        "[3] M. Chiari, M. De Pascalis, M. Pradella, \"Static analysis of infrastructure as code: a survey,\" ICSA-C, 2022.",
        "[4] E. Malul, Y. Meidan, Y. Mirsky, Y. Elovici, \"GenKubeSec: LLM-based Kubernetes misconfiguration detection,\" arXiv, 2024.",
        "[5] P. Lewis et al., \"Retrieval-augmented generation for knowledge-intensive NLP tasks,\" NeurIPS, 2020.",
        "[6] H. Pearce et al., \"Asleep at the keyboard? Assessing the security of GitHub Copilot's code contributions,\" IEEE S&P, 2022.",
        "[7] Microsoft Learn, Cloud Adoption Framework and Azure Well-Architected Framework, accessed 27 Oct 2026.",
    ], 16)
    from pptx.enum.text import MSO_AUTO_SIZE
    rect.text_frame.auto_size = MSO_AUTO_SIZE.NONE
    rect.text_frame.word_wrap = True

    prs.save(str(OUTPUT))
    print("saved", OUTPUT.name, "slides:", len(prs.slides))
    return 0


def _title(slide, text):
    t = slide.shapes.title
    t.left, t.top, t.width, t.height = Emu(460248), Emu(681037), Emu(10515600), Emu(576696)
    t.text_frame.text = text
    for r in t.text_frame.paragraphs[0].runs:
        r.font.size = Pt(30)
        r.font.bold = True
    t.text_frame.paragraphs[0].alignment = PP_ALIGN.LEFT


if __name__ == "__main__":
    raise SystemExit(main())
