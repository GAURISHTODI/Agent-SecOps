"""Generate the BCSE497J Project-I report in the prescribed VIT format.

Formatting rules taken directly from the supplied template:
  Level-1 heading  Times New Roman 14, Bold, UPPER CASE, line spacing 1.5
  Level-2 heading  Times New Roman 13, Bold, Title Case, line spacing 1.5
  Level-3 heading  Times New Roman 12, Bold + Italic, Title Case, spacing 1.5
  Body             Times New Roman 12, line spacing 1.15
  Title page       Title 16 Bold UPPER, names 13 Bold UPPER, spacing 1.5

Run:  python scripts/build_report.py
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "3 BCSE497J Project I Report - Template.docx"
OUTPUT = ROOT / "Agent SecOps - BCSE497J Project-I Report.docx"

FONT = "Times New Roman"


# ----------------------------------------------------------------------
# low-level helpers
# ----------------------------------------------------------------------

def _set_run(run, size, bold=False, italic=False):
    run.font.name = FONT
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    # East-Asian font mapping, else Word may substitute on some machines.
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rfonts.set(qn(attr), FONT)


def para(doc, text="", size=12, bold=False, italic=False, spacing=1.15,
         align=None, space_after=6, space_before=0, indent_left=None):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.line_spacing = spacing
    pf.space_after = Pt(space_after)
    pf.space_before = Pt(space_before)
    if align is not None:
        p.alignment = align
    if indent_left is not None:
        pf.left_indent = Inches(indent_left)
    if text:
        _set_run(p.add_run(text), size, bold, italic)
    return p


def h1(doc, text):
    return para(doc, text.upper(), size=14, bold=True, spacing=1.5,
                space_before=12, space_after=8)


def h2(doc, text):
    return para(doc, text, size=13, bold=True, spacing=1.5,
                space_before=10, space_after=6)


def h3(doc, text):
    return para(doc, text, size=12, bold=True, italic=True, spacing=1.5,
                space_before=8, space_after=4)


def body(doc, text):
    return para(doc, text, size=12, spacing=1.15,
                align=WD_ALIGN_PARAGRAPH.JUSTIFY, space_after=8)


def bullet(doc, text, bold_lead=None):
    p = doc.add_paragraph(style="List Bullet")
    pf = p.paragraph_format
    pf.line_spacing = 1.15
    pf.space_after = Pt(4)
    pf.left_indent = Inches(0.35)
    if bold_lead:
        _set_run(p.add_run(bold_lead), 12, bold=True)
        _set_run(p.add_run(text), 12)
    else:
        _set_run(p.add_run(text), 12)
    return p


def caption(doc, text):
    return para(doc, text, size=11, italic=False, spacing=1.0,
                align=WD_ALIGN_PARAGRAPH.CENTER, space_after=10, space_before=4)


FIGDIR = ROOT / "docs" / "figures"


def figure(doc, filename, label, width_in=6.1):
    """Insert a generated figure, centred, with its numbered caption."""
    path = FIGDIR / filename
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(2)
    if path.exists():
        p.add_run().add_picture(str(path), width=Inches(width_in))
    else:
        r = p.add_run(f"[missing figure: {filename}]")
        _set_run(r, 11, italic=True)
        r.font.color.rgb = RGBColor(0x88, 0x88, 0x88)
    caption(doc, label)


def page_break(doc):
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def simple_table(doc, headers, rows, widths=None, font_size=11):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, htxt in enumerate(headers):
        c = t.rows[0].cells[i]
        c.text = ""
        p = c.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(2)
        _set_run(p.add_run(htxt), font_size, bold=True)
    for row in rows:
        cells = t.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.line_spacing = 1.0
            _set_run(p.add_run(str(val)), font_size)
    if widths:
        for r in t.rows:
            for i, w in enumerate(widths):
                r.cells[i].width = Inches(w)
    para(doc, "", space_after=2)
    return t


def borderless_table(doc, rows, widths, font_size=12):
    t = doc.add_table(rows=0, cols=len(widths))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for row in rows:
        cells = t.add_row().cells
        for i, (val, bold) in enumerate(row):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.line_spacing = 1.5
            if i == len(widths) - 1:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _set_run(p.add_run(str(val)), font_size, bold=bold)
            cells[i].width = Inches(widths[i])
    return t


def extract_logo() -> io.BytesIO | None:
    if not TEMPLATE.exists():
        return None
    with zipfile.ZipFile(TEMPLATE) as z:
        for name in ("word/media/image1.jpg",):
            if name in z.namelist():
                return io.BytesIO(z.read(name))
    return None


# ----------------------------------------------------------------------
# document
# ----------------------------------------------------------------------

def build() -> None:
    doc = Document()

    # base style
    normal = doc.styles["Normal"]
    normal.font.name = FONT
    normal.font.size = Pt(12)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)

    for s in doc.sections:
        s.top_margin = Inches(1)
        s.bottom_margin = Inches(1)
        s.left_margin = Inches(1.25)
        s.right_margin = Inches(1)

    # ---------------- title page ----------------
    para(doc, "BCSE497J - Project-I", size=14, bold=True, spacing=1.5,
         align=WD_ALIGN_PARAGRAPH.CENTER, space_after=24)

    para(doc,
         "AGENT SECOPS: AN AI-DRIVEN SECOPS AGENT FOR CAF/WAF-ALIGNED "
         "INFRASTRUCTURE-AS-CODE PIPELINES",
         size=16, bold=True, spacing=1.5,
         align=WD_ALIGN_PARAGRAPH.CENTER, space_after=22)

    para(doc, "By", size=13, spacing=1.5,
         align=WD_ALIGN_PARAGRAPH.CENTER, space_after=10)

    borderless_table(doc, [
        [("23BCE0196", True), ("BHUMIKA SINGH", True)],
        [("23BCE0958", True), ("AKSHAT GUPTA", True)],
        [("23BCI0262", True), ("GAURISH TODI", True)],
    ], widths=[1.6, 2.6], font_size=13)

    para(doc, "", space_after=14)
    para(doc, "Under the Supervision of", size=13, spacing=1.5,
         align=WD_ALIGN_PARAGRAPH.CENTER, space_after=8)

    borderless_table(doc, [
        [("Dr. S. M. Farooq", True)],
        [("[Designation]", False)],
        [("School of Computer Science and Engineering", False)],
    ], widths=[4.6], font_size=12)

    para(doc, "", space_after=16)
    para(doc, "B.Tech.", size=13, spacing=1.5,
         align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
    para(doc, "in", size=13, spacing=1.5,
         align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
    para(doc, "Computer Science and Engineering", size=13, spacing=1.5,
         align=WD_ALIGN_PARAGRAPH.CENTER, space_after=18)

    logo = extract_logo()
    if logo:
        lp = doc.add_paragraph()
        lp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        lp.add_run().add_picture(logo, width=Inches(2.6))
        lp.paragraph_format.space_after = Pt(10)

    para(doc, "School of Computer Science and Engineering", size=13, bold=True,
         spacing=1.5, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=18)
    para(doc, "September 2026", size=13, bold=True, spacing=1.5,
         align=WD_ALIGN_PARAGRAPH.CENTER, space_after=0)

    page_break(doc)

    # ---------------- abstract ----------------
    para(doc, "ABSTRACT", size=14, bold=True, spacing=1.5,
         align=WD_ALIGN_PARAGRAPH.CENTER, space_after=12)

    body(doc,
         "Modern engineering teams provision cloud infrastructure declaratively "
         "using Terraform, delivered through CI/CD pipelines such as GitHub "
         "Actions into Azure, AWS or GCP. Cloud providers publish extensive "
         "governance guidance - Microsoft's Cloud Adoption Framework (CAF) and "
         "the Well-Architected Framework (WAF) - covering security, reliability, "
         "cost, operational excellence and sustainability. This guidance is "
         "narrative documentation rather than executable policy, so it is rarely "
         "verified automatically before a deployment reaches the cloud. Existing "
         "policy-as-code tools such as Checkov, Open Policy Agent and HashiCorp "
         "Sentinel evaluate only rules an engineer has already encoded; they "
         "cannot reason about the architectural intent expressed in framework "
         "documentation.")

    body(doc,
         "This project presents Agent SecOps, an AI-driven compliance gate that "
         "is positioned between the terraform plan and terraform apply stages of "
         "a CI/CD pipeline. The agent parses the Terraform plan JSON, normalises "
         "every proposed resource into a cloud-agnostic representation, and "
         "evaluates it through three layers: a deterministic rule engine "
         "implementing twenty-two CAF and WAF checks, a policy-aware reasoning "
         "layer that retrieves the framework guidance relevant to each resource "
         "kind and identifies violations that no rule encodes, and an "
         "organisational policy layer supporting severity thresholds and "
         "time-boxed waivers. The gate returns a pass, remediate or block verdict "
         "with a plain-language report naming the exact pillar violated and a "
         "suggested remediation.")

    body(doc,
         "The prototype was evaluated against a labelled test set of forty-two "
         "seeded misconfigurations spanning Azure, AWS and GCP. The deterministic "
         "rules alone detected 88.1 per cent of violations, while the complete "
         "agent detected 100 per cent, with zero false positives on a compliant "
         "module and a median gate latency below ten milliseconds. The system was "
         "additionally validated against a live Azure subscription, where it "
         "gated and approved a real deployment of four resources.")

    para(doc, "", space_after=6)
    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.15
    _set_run(p.add_run("Keywords - "), 12, bold=True)
    _set_run(p.add_run(
        "Infrastructure as Code, Cloud Adoption Framework, Well-Architected "
        "Framework, Policy as Code, DevSecOps, Large Language Models, "
        "Terraform, CI/CD, Cloud Governance."), 12)

    page_break(doc)

    # ---------------- table of contents ----------------
    para(doc, "TABLE OF CONTENTS", size=14, bold=True, spacing=1.5,
         align=WD_ALIGN_PARAGRAPH.CENTER, space_after=12)

    toc_rows = [
        ("", "Abstract", "i"),
        ("1.", "INTRODUCTION", "1"),
        ("", "1.1 Background", "1"),
        ("", "1.2 Motivation", "1"),
        ("", "1.3 Scope of the Project", "2"),
        ("2.", "PROJECT DESCRIPTION AND GOALS", "3"),
        ("", "2.1 Literature Review", "3"),
        ("", "2.2 Research Gap", "6"),
        ("", "2.3 Objectives", "7"),
        ("", "2.4 Problem Statement", "8"),
        ("", "2.5 Project Plan", "8"),
        ("3.", "TECHNICAL SPECIFICATION", "11"),
        ("", "3.1 Requirements", "11"),
        ("", "3.1.1 Functional", "11"),
        ("", "3.1.2 Non-Functional", "12"),
        ("", "3.2 Feasibility Study", "13"),
        ("", "3.2.1 Technical Feasibility", "13"),
        ("", "3.2.2 Economic Feasibility", "14"),
        ("", "3.2.3 Social Feasibility", "14"),
        ("", "3.3 System Specification", "15"),
        ("", "3.3.1 Hardware Specification", "15"),
        ("", "3.3.2 Software Specification", "15"),
        ("4.", "DESIGN APPROACH AND DETAILS", "17"),
        ("", "4.1 System Architecture", "17"),
        ("", "4.2 Design", "19"),
        ("", "4.2.1 Data Flow Diagram", "19"),
        ("", "4.2.2 Use Case Diagram", "20"),
        ("", "4.2.3 Class Diagram", "21"),
        ("", "4.2.4 Sequence Diagram", "22"),
        ("5.", "REFERENCES", "23"),
    ]

    t = doc.add_table(rows=1, cols=3)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = ["Sl.No", "Contents", "Page No."]
    for i, htxt in enumerate(hdr):
        c = t.rows[0].cells[i]
        c.text = ""
        p = c.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.line_spacing = 1.5
        _set_run(p.add_run(htxt), 12, bold=True)
    for sl, content, page in toc_rows:
        cells = t.add_row().cells
        is_major = content.isupper()
        for i, (val, al) in enumerate([
            (sl, WD_ALIGN_PARAGRAPH.CENTER),
            (content, WD_ALIGN_PARAGRAPH.LEFT),
            (page, WD_ALIGN_PARAGRAPH.CENTER),
        ]):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            p.alignment = al
            p.paragraph_format.line_spacing = 1.5
            p.paragraph_format.space_after = Pt(0)
            _set_run(p.add_run(val), 12, bold=is_major)
    for r in t.rows:
        r.cells[0].width = Inches(0.8)
        r.cells[1].width = Inches(4.4)
        r.cells[2].width = Inches(1.0)

    para(doc, "", space_after=4)
    para(doc, "Note: page numbers to be refreshed after screenshots and "
              "diagrams are inserted.", size=10, italic=True,
         align=WD_ALIGN_PARAGRAPH.CENTER)

    page_break(doc)

    # ================= 1. INTRODUCTION =================
    h1(doc, "1. Introduction")

    h2(doc, "1.1 Background")
    body(doc,
         "Cloud infrastructure is now provisioned as code. Instead of clicking "
         "through a portal, engineers describe the desired state of a cloud "
         "environment in a declarative language such as Terraform, commit that "
         "description to version control, and allow a CI/CD pipeline to apply it. "
         "This practice, known as Infrastructure as Code (IaC), has made "
         "provisioning repeatable and auditable, but it has also made "
         "misconfiguration reproducible and fast.")
    body(doc,
         "To help organisations adopt the cloud responsibly, Microsoft publishes "
         "two complementary bodies of guidance. The Cloud Adoption Framework "
         "(CAF) addresses portfolio-level governance: resource naming, tagging, "
         "ownership, landing-zone boundaries, cost attribution and identity. The "
         "Well-Architected Framework (WAF) addresses workload-level design "
         "quality across the pillars of security, reliability, cost "
         "optimisation, operational excellence, performance efficiency and "
         "sustainability. Both are authoritative and widely referenced.")
    body(doc,
         "Crucially, both are written as prose. They are documents intended for "
         "human architects to read and apply with judgement, not artefacts that "
         "a pipeline can execute. Consequently, in most organisations, the "
         "question of whether a proposed change actually respects CAF and WAF is "
         "answered - if at all - by a manual architecture review that does not "
         "scale to the volume of daily pull requests.")

    h2(doc, "1.2 Motivation")
    body(doc,
         "Cloud misconfiguration remains the single most preventable category of "
         "cloud security incident. Industry reporting attributes approximately "
         "23 per cent of cloud security incidents directly to misconfigured "
         "resources, Gartner projects that close to 99 per cent of cloud "
         "security failures will be the customer's own fault - predominantly "
         "configuration errors - and industry benchmarks place the average dwell "
         "time of an undetected misconfiguration beyond 180 days.")
    body(doc,
         "Existing tooling only partially addresses this. Static scanners such as "
         "Checkov, tfsec, Open Policy Agent and HashiCorp Sentinel are valuable, "
         "but each enforces a fixed library of rules that somebody has already "
         "written. They cannot evaluate a resource against an architectural "
         "principle that was never converted into a rule, and they must be "
         "maintained separately for each cloud provider.")
    body(doc,
         "This gap is the motivation for the project. If CAF and WAF guidance can "
         "be made machine-readable and reasoned over automatically at the precise "
         "moment before infrastructure is created, then a broad class of "
         "governance and security failures can be prevented rather than detected "
         "after the fact - before any cost is incurred and before any resource is "
         "exposed.")

    h2(doc, "1.3 Scope of the Project")
    body(doc,
         "The project delivers a working proof-of-concept compliance gate that "
         "operates on Terraform plan output inside a GitHub Actions pipeline. Its "
         "scope covers the parsing and normalisation of Terraform plan JSON, a "
         "deterministic rule engine covering the CAF governance areas and all six "
         "WAF pillars, a reasoning layer that evaluates resources against "
         "retrieved framework guidance, an organisational policy layer with "
         "severity thresholds and expiring waivers, and report generation in "
         "Markdown, JSON and SARIF formats.")
    body(doc,
         "The gate logic is deliberately cloud-agnostic. Provider-specific "
         "resource types from Azure, AWS and GCP are mapped onto a common set of "
         "canonical resource kinds so that a single rule applies across all three "
         "clouds. Validation is performed against a labelled corpus of seeded "
         "misconfigurations and against a live Azure deployment.")
    body(doc,
         "The following are explicitly outside scope: runtime or post-deployment "
         "monitoring, remediation of resources that already exist, support for "
         "IaC languages other than Terraform, and production-scale performance "
         "engineering. The deliverable is a validated prototype at Technology "
         "Readiness Level 4, not a commercially hardened product.")

    page_break(doc)

    # ================= 2. PROJECT DESCRIPTION AND GOALS =================
    h1(doc, "2. Project Description and Goals")

    h2(doc, "2.1 Literature Review")
    body(doc,
         "The literature relevant to this project falls into three streams: "
         "empirical studies of defects in Infrastructure as Code, static analysis "
         "and policy-as-code tooling, and the emerging application of large "
         "language models to configuration and code security.")

    h3(doc, "A. Security and Quality Defects in Infrastructure as Code")
    body(doc,
         "Rahman, Parnin and Williams [1] established the foundational empirical "
         "result in this area with their study of security smells in IaC scripts, "
         "identifying seven recurring insecure coding patterns - including "
         "hard-coded secrets, use of HTTP without TLS, and overly permissive "
         "access - across a large corpus of Puppet scripts. Their subsequent "
         "replication study across Ansible and Chef [2] confirmed that these "
         "patterns generalise beyond a single IaC language, which supports the "
         "cloud-agnostic design adopted in this project.")
    body(doc,
         "Guerriero et al. [3] surveyed industrial practitioners and reported "
         "that, while IaC adoption is widespread, tooling for quality assurance "
         "and compliance verification lags well behind adoption, and that "
         "practitioners rely heavily on manual review. Bhuiyan and Rahman [4] "
         "further characterised how insecure patterns cluster together within the "
         "same scripts, indicating that a single defective module frequently "
         "violates several principles at once - an observation reflected in the "
         "grouped, per-resource reporting used in this work.")
    body(doc,
         "Opdebeeck, Zerouali and De Roover [5] examined variable-related smells "
         "in Ansible, and Saavedra and Ferreira [6] proposed GLITCH, a polyglot "
         "intermediate representation enabling security smell detection across "
         "multiple IaC technologies. GLITCH is particularly relevant here: its "
         "central insight - that normalising heterogeneous IaC into a common "
         "representation allows one analysis to serve many technologies - is the "
         "same insight underpinning the canonical resource model described in "
         "Section 4.1.")

    h3(doc, "B. Static Analysis and Policy-as-Code Tooling")
    body(doc,
         "Chiari, De Pascalis and Pradella [7] surveyed static analysis "
         "techniques for IaC and classified the available tools by the defect "
         "classes they target. Their survey makes clear that the overwhelming "
         "majority of production tooling is rule-based: correctness is defined by "
         "an explicit, hand-authored predicate. Sandobalin, Insfran and Abrahao "
         "[8] compared model-driven and code-centric approaches to IaC support "
         "and found that both improve reliability but neither reasons about "
         "architectural intent.")
    body(doc,
         "In industrial practice, four tools dominate. Checkov and tfsec perform "
         "static scanning of IaC source using rule libraries authored in Python "
         "and YAML. Open Policy Agent [12] provides a general-purpose policy "
         "engine in which rules are expressed in the Rego language and evaluated "
         "against arbitrary JSON input. HashiCorp Sentinel [13] provides "
         "policy-as-code within the Terraform Cloud and Enterprise ecosystem. "
         "Table 1 summarises their characteristics relative to the present work.")

    para(doc, "", space_after=2)
    simple_table(doc,
                 ["Tool", "Scope", "Decision basis", "Principal limitation"],
                 [
                     ["Checkov / tfsec", "Static IaC scanning",
                      "Pre-written rules (Python / YAML)",
                      "Fixed rule library; no framework reasoning"],
                     ["HashiCorp Sentinel", "Terraform Cloud / Enterprise",
                      "Hand-authored Sentinel policies",
                      "Vendor-locked; policies authored per organisation"],
                     ["Open Policy Agent", "General purpose (K8s, IaC, APIs)",
                      "Rego rules over JSON input",
                      "Steep learning curve; rules still hand-written"],
                     ["Agent SecOps (this work)",
                      "Terraform -> any CI/CD -> any cloud",
                      "Deterministic rules + reasoning over CAF/WAF pillars",
                      "Proof-of-concept stage; reasoning layer advisory by default"],
                 ],
                 widths=[1.35, 1.55, 1.75, 1.85], font_size=10)
    caption(doc, "Table 1. Comparison of policy-as-code tooling with the "
                 "proposed approach")

    h3(doc, "C. Large Language Models for Configuration and Code Security")
    body(doc,
         "The application of large language models to code has advanced rapidly "
         "since Chen et al. [9] demonstrated competent program synthesis from "
         "natural-language specifications, and since Brown et al. [10] "
         "established that sufficiently large models perform useful tasks from "
         "few examples. Lewis et al. [11] introduced retrieval-augmented "
         "generation, in which a model is supplied with retrieved documents "
         "relevant to the query rather than relying solely on parametric "
         "knowledge. This technique is directly applicable to framework "
         "compliance, where the authoritative guidance is documentary.")
    body(doc,
         "Security outcomes from model-generated code are, however, not "
         "automatically favourable. Pearce et al. [14] showed that a significant "
         "proportion of code produced by GitHub Copilot in security-sensitive "
         "contexts contained exploitable weaknesses. This finding directly "
         "motivates a central design decision in the present work: the reasoning "
         "layer is advisory by default and cannot, without explicit "
         "organisational opt-in, cause a deployment to be blocked.")
    body(doc,
         "Two recent studies establish the immediate precedent for this project. "
         "Malul et al. [15] proposed GenKubeSec, an LLM-based system for "
         "detecting, localising, reasoning about and remediating Kubernetes "
         "misconfigurations, reporting detection performance competitive with "
         "and in places superior to established rule-based scanners. Vo, Dao and "
         "Fukuda [16] applied large language models to code smell detection "
         "specifically in Terraform IaC and likewise reported that models "
         "identify defect classes that rule-based tooling does not cover.")
    body(doc,
         "Both studies analyse IaC source artefacts in isolation. Neither embeds "
         "the model as an enforcing gate within a deployment pipeline, neither "
         "evaluates against a published governance framework such as CAF or WAF, "
         "and neither addresses the multi-cloud case. That combination defines "
         "the gap this project addresses.")

    h2(doc, "2.2 Research Gap")
    body(doc,
         "Synthesising the literature reviewed above, four specific gaps are "
         "identified.")
    bullet(doc, "Static policy-as-code tools detect violations only of rules "
                "that have already been hand-authored. Framework guidance that "
                "was never codified into an explicit predicate is invisible to "
                "them, and each cloud provider requires a separately maintained "
                "rule set.",
           bold_lead="Rule-bound detection. ")
    bullet(doc, "Recent LLM-based work (GenKubeSec [15]; Vo et al. [16]) "
                "demonstrates that models can out-detect rule-based scanners for "
                "Kubernetes manifests and Terraform source respectively, but "
                "operates on static artefacts rather than as an enforcing "
                "control inside a CI/CD pipeline.",
           bold_lead="Analysis without enforcement. ")
    bullet(doc, "No existing study evaluates IaC changes against the specific "
                "governance structure of Microsoft's Cloud Adoption Framework "
                "and Well-Architected Framework, mapping each finding to the "
                "pillar it violates.",
           bold_lead="Absence of framework grounding. ")
    bullet(doc, "Prior work is generally single-provider. A gate that normalises "
                "Azure, AWS and GCP resources into shared abstractions, so that "
                "one rule serves all three, has not been demonstrated.",
           bold_lead="Single-cloud scope. ")
    body(doc,
         "This project addresses all four: it embeds a reasoning agent directly "
         "as a pipeline gate, grounds every finding in a named CAF or WAF pillar, "
         "and applies a single cloud-agnostic rule set across three providers.")

    h2(doc, "2.3 Objectives")
    body(doc, "The project pursues the following specific and measurable "
              "objectives.")
    bullet(doc, "To design and implement an agent that parses Terraform plan "
                "JSON and evaluates each proposed resource against CAF "
                "governance areas and the WAF pillars, producing a pass, "
                "remediate or block verdict.",
           bold_lead="O1. ")
    bullet(doc, "To normalise provider-specific resource types from Azure, AWS "
                "and GCP into a canonical resource model so that gate logic "
                "remains cloud-agnostic and verifiable by automated test.",
           bold_lead="O2. ")
    bullet(doc, "To implement a policy-aware reasoning layer that retrieves the "
                "framework guidance relevant to each resource kind and reports "
                "violations of architectural intent that no deterministic rule "
                "encodes.",
           bold_lead="O3. ")
    bullet(doc, "To integrate the agent as an enforcing gate within a GitHub "
                "Actions workflow such that terraform apply is unreachable when "
                "the verdict is block, and a human-readable compliance report is "
                "published to the pull request.",
           bold_lead="O4. ")
    bullet(doc, "To quantify effectiveness against a labelled corpus of seeded "
                "misconfigurations, reporting detection rate, false-positive rate "
                "on compliant infrastructure, and the marginal contribution of "
                "the reasoning layer over deterministic rules alone.",
           bold_lead="O5. ")
    bullet(doc, "To validate the complete pipeline against a live cloud "
                "subscription while constraining the deployed footprint to "
                "negligible cost.",
           bold_lead="O6. ")

    h2(doc, "2.4 Problem Statement")
    body(doc,
         "Cloud providers publish authoritative architectural guidance in the "
         "form of the Cloud Adoption Framework and the Well-Architected "
         "Framework, yet this guidance exists only as narrative documentation. "
         "Nothing in a conventional CI/CD pipeline prevents an engineer from "
         "merging a Terraform change that quietly violates it, and the violation "
         "typically becomes visible only after the resource has been created, "
         "has begun incurring cost, and may already be exposed.")
    body(doc,
         "Existing policy-as-code tools mitigate but do not solve this problem, "
         "because they can only detect violations of rules that a human has "
         "already anticipated and encoded, and because they require separate rule "
         "sets per cloud provider. Manual architecture review, the only mechanism "
         "capable of judging framework intent, does not scale across dozens of "
         "daily pull requests and multiple cloud platforms.")
    body(doc,
         "The problem addressed by this project is therefore: how can a CI/CD "
         "pipeline automatically evaluate a proposed infrastructure change "
         "against narrative cloud governance frameworks - including intent that "
         "was never codified as an explicit rule - and reach a reliable, "
         "explainable pass or block decision before any resource is created, "
         "consistently across multiple cloud providers?")

    h2(doc, "2.5 Project Plan")
    body(doc,
         "The project is executed over a single semester in six phases. Phase 1 "
         "covers problem formulation and the literature survey. Phase 2 covers "
         "architectural design and the definition of the canonical resource "
         "model. Phase 3 implements the plan parser and the deterministic rule "
         "engine. Phase 4 implements the knowledge base, the reasoning layer and "
         "the policy engine. Phase 5 covers CI/CD integration, the Terraform "
         "modules and cloud provisioning. Phase 6 covers evaluation, the "
         "benchmark harness, the demonstration dashboard and documentation. "
         "Figure 1 presents the schedule as a Gantt chart.")

    figure(doc, "fig1_gantt.png", "Fig. 1. Project schedule (Gantt chart)",
           width_in=6.2)

    h3(doc, "Team Roles and Module Ownership")
    body(doc,
         "Work is partitioned into three modules with clean interfaces, allowing "
         "the members to develop and test independently. Table 2 records the "
         "allocation and Table 3 records the specific artefacts owned by each "
         "member.")

    simple_table(doc,
                 ["Reg. No.", "Name", "Module", "Weight"],
                 [
                     ["23BCE0196", "Bhumika Singh",
                      "CI/CD pipeline, Terraform infrastructure, Azure "
                      "provisioning, CLI and report rendering", "Light"],
                     ["23BCE0958", "Akshat Gupta",
                      "Plan parsing, canonical resource model and the "
                      "deterministic CAF/WAF rule engine", "Medium"],
                     ["23BCI0262", "Gaurish Todi",
                      "Knowledge base, reasoning layer, orchestration engine, "
                      "policy engine, evaluation harness and dashboard", "Major"],
                 ],
                 widths=[0.95, 1.25, 3.3, 0.85], font_size=10)
    caption(doc, "Table 2. Allocation of work among team members")

    simple_table(doc,
                 ["Member", "Files and folders owned", "Principal contribution"],
                 [
                     ["Gaurish Todi\n(23BCI0262)",
                      "agent/engine.py; agent/config.py; agent/reasoner/ "
                      "(base.py, offline.py, llm.py); agent/knowledge/"
                      "caf_waf_kb.yaml; dashboard/; scripts/benchmark.py; "
                      "tests/test_engine.py; docs/architecture.md",
                      "Designed the three-layer architecture; authored the "
                      "CAF/WAF knowledge base and the retrieval-based reasoning "
                      "layer; implemented verdict orchestration, severity "
                      "thresholds and expiring waivers; built the evaluation "
                      "harness that measures detection rate, false positives and "
                      "the marginal contribution of reasoning; built the "
                      "demonstration dashboard."],
                     ["Akshat Gupta\n(23BCE0958)",
                      "agent/models.py; agent/plan_parser.py; agent/rules/ "
                      "(base.py, caf.py, waf.py); tests/test_plan_parser.py; "
                      "tests/test_rules.py",
                      "Defined the cloud-agnostic data model; implemented "
                      "Terraform plan JSON parsing and the canonical kind "
                      "mapping that makes the gate multi-cloud; authored all "
                      "twenty-two deterministic CAF and WAF rules with their "
                      "framework rationale; wrote bidirectional rule tests "
                      "covering both detection and false-positive avoidance."],
                     ["Bhumika Singh\n(23BCE0196)",
                      ".github/workflows/secops-gate.yml; infra/demo/; "
                      "examples/terraform/noncompliant/; examples/plans/; "
                      "scripts/azure-*.sh; agent/report.py; agent/cli.py; "
                      "policies/policy.yaml; docs/azure-setup.md",
                      "Built the GitHub Actions workflow that positions the gate "
                      "between plan and apply; authored the compliant Terraform "
                      "module and the seeded misconfiguration module; configured "
                      "Azure OIDC federation and least-privilege access; "
                      "implemented the CLI exit-code contract and the Markdown, "
                      "JSON and SARIF report renderers."],
                 ],
                 widths=[1.1, 2.3, 3.1], font_size=9)
    caption(doc, "Table 3. Detailed contribution of each team member")

    page_break(doc)

    # ================= 3. TECHNICAL SPECIFICATION =================
    h1(doc, "3. Technical Specification")

    h2(doc, "3.1 Requirements")

    h3(doc, "3.1.1 Functional")
    reqs = [
        ("FR1", "Plan ingestion", "The system shall accept Terraform plan output "
         "in JSON form, as produced by terraform show -json, and shall reject "
         "malformed input with an actionable diagnostic message."),
        ("FR2", "Resource normalisation", "The system shall map provider-specific "
         "resource types from Azure, AWS and GCP onto canonical resource kinds, "
         "and shall correctly interpret create, update, replace and delete "
         "actions."),
        ("FR3", "Deterministic evaluation", "The system shall evaluate each "
         "mutating resource against a registry of CAF and WAF rules, each "
         "returning a finding annotated with rule identifier, pillar, severity, "
         "explanation and remediation."),
        ("FR4", "Framework reasoning", "The system shall retrieve the framework "
         "guidance relevant to each resource kind and identify violations of "
         "architectural intent not covered by any deterministic rule, without "
         "duplicating existing findings."),
        ("FR5", "Policy application", "The system shall apply organisational "
         "severity thresholds, rule enable/disable and parameter overrides, and "
         "time-boxed waivers loaded from an external configuration file."),
        ("FR6", "Verdict production", "The system shall aggregate all findings "
         "into a single verdict of pass, remediate or block, and shall expose "
         "that verdict as a process exit code for pipeline consumption."),
        ("FR7", "Report generation", "The system shall render results as a "
         "Markdown report for pull-request review, a JSON document for machine "
         "consumption, and a SARIF 2.1.0 file for security tooling."),
        ("FR8", "Pipeline integration", "The system shall execute within a "
         "GitHub Actions workflow positioned between the plan and apply stages, "
         "publish its report to the pull request, and prevent apply on a block "
         "verdict."),
        ("FR9", "Demonstration interface", "The system shall provide a local web "
         "dashboard presenting the verdict, findings by pillar and severity, and "
         "the measured benchmark results."),
    ]
    for rid, name, text in reqs:
        bullet(doc, text, bold_lead=f"{rid} - {name}: ")

    h3(doc, "3.1.2 Non-Functional")
    nfrs = [
        ("NFR1", "Performance", "The gate shall complete evaluation of a typical "
         "plan within one second, so that it imposes no perceptible delay on the "
         "pipeline. The measured median is below ten milliseconds."),
        ("NFR2", "Precision", "The gate shall produce no false positives on "
         "compliant infrastructure, since a gate that fails correct code is "
         "disabled by the team that owns it."),
        ("NFR3", "Determinism", "Blocking decisions shall derive only from "
         "deterministic rules, so that identical input always yields an identical "
         "verdict."),
        ("NFR4", "Availability tolerance", "Failure or unavailability of the "
         "optional model endpoint shall degrade the gate to deterministic "
         "evaluation, and shall never break the pipeline."),
        ("NFR5", "Cost efficiency", "Routine operation shall incur no cloud cost. "
         "Where the optional model reasoner is enabled, per-run cost shall be "
         "bounded by resource caps, prompt redaction and response caching."),
        ("NFR6", "Portability", "The gate shall depend only on the Python "
         "standard library and PyYAML, and shall run without modification on a "
         "hosted CI runner."),
        ("NFR7", "Security", "No long-lived credential shall be stored in the "
         "repository; pipeline authentication shall use OIDC federation, and "
         "secrets shall be redacted before any external transmission."),
        ("NFR8", "Maintainability", "Rules shall be independently registered "
         "units carrying their own documentation, and organisational tuning shall "
         "require editing configuration only, not source code."),
        ("NFR9", "Auditability", "Every finding shall name the framework pillar "
         "it violates and its provenance, distinguishing deterministic findings "
         "from reasoned ones."),
    ]
    for rid, name, text in nfrs:
        bullet(doc, text, bold_lead=f"{rid} - {name}: ")

    h2(doc, "3.2 Feasibility Study")

    h3(doc, "3.2.1 Technical Feasibility")
    body(doc,
         "The project is technically feasible and has been demonstrated in "
         "practice. Every integration point is a documented, stable interface: "
         "Terraform publishes a versioned JSON plan schema, GitHub Actions "
         "provides workflow hooks and OIDC token issuance, and Azure exposes "
         "federated credential exchange. No reverse engineering or unsupported "
         "interface is required.")
    body(doc,
         "The runtime dependency footprint is deliberately minimal - the Python "
         "standard library together with PyYAML - which removes installation risk "
         "on hosted runners. The optional model reasoner communicates over plain "
         "HTTPS rather than a vendor SDK, so it introduces no additional "
         "dependency. The complete test suite comprises sixty-three automated "
         "tests, all passing, and the system has been validated end to end "
         "against a live Azure subscription.")
    figure(doc, "fig8_benchmark.png",
           "Fig. 2. Measured detection performance against the seeded "
           "misconfiguration corpus", width_in=6.3)

    body(doc,
         "The principal technical risk is the non-determinism of the reasoning "
         "layer. This is mitigated architecturally rather than by tuning: the "
         "reasoning layer cannot block a deployment unless an organisation "
         "explicitly opts in, and a deterministic offline reasoner provides an "
         "equivalent, zero-cost control path.")

    h3(doc, "3.2.2 Economic Feasibility")
    body(doc,
         "The economic profile of the project is unusually favourable because the "
         "gate evaluates a plan rather than a deployment. Evaluation is pure "
         "computation over a local JSON file and therefore incurs no cloud cost "
         "whatsoever; the pipeline executes on the free tier of GitHub-hosted "
         "runners.")
    body(doc,
         "The validation footprint provisioned in Azure was constrained to a "
         "resource group, a locally-redundant storage account and a Log Analytics "
         "workspace subject to a hard daily ingestion quota. Measured steady-state "
         "cost is approximately four rupees per month. Expensive resource classes "
         "- virtual machines, managed Kubernetes, managed databases and private "
         "endpoints - are exercised entirely through plan-only fixtures at zero "
         "cost, which is a direct consequence of gating at plan time.")
    body(doc,
         "Where the optional model reasoner is enabled, cost is bounded by a cap "
         "on the number of resources submitted per run, a limit on output tokens, "
         "prompt redaction and a response cache keyed on plan content. The "
         "resulting per-run cost is below one-tenth of a rupee. Set against the "
         "documented cost of a single cloud misconfiguration incident, the return "
         "on investment is substantial.")

    h3(doc, "3.2.3 Social Feasibility")
    body(doc,
         "The system is designed for adoption rather than imposition. Findings "
         "are expressed in plain language, cite the specific framework pillar "
         "violated, and include a copy-ready configuration fix, so the gate "
         "functions as a teaching mechanism as well as a control. A report-only "
         "mode allows an organisation with an existing backlog of violations to "
         "adopt the gate incrementally before enabling enforcement.")
    body(doc,
         "Ethically, the design keeps human authority over automated judgement. "
         "The reasoning layer is advisory by default; waivers require a stated "
         "reason and expire automatically, preventing indefinite silent "
         "suppression of known risk; and no secret material is transmitted "
         "externally. The system augments the reviewer rather than replacing the "
         "role, redirecting scarce architectural expertise from routine checks "
         "towards genuinely novel design questions.")

    h2(doc, "3.3 System Specification")

    h3(doc, "3.3.1 Hardware Specification")
    simple_table(doc,
                 ["Component", "Development machine", "CI runner (GitHub-hosted)"],
                 [
                     ["Processor", "x86-64, quad-core, 2.0 GHz or higher",
                      "2 vCPU"],
                     ["Memory (RAM)", "8 GB minimum, 16 GB recommended", "7 GB"],
                     ["Storage", "10 GB free disk space", "14 GB SSD"],
                     ["Graphics Processing Unit",
                      "Not required - no model training is performed",
                      "Not applicable"],
                     ["Monitor", "1920 x 1080 recommended for the dashboard",
                      "Not applicable"],
                     ["Network", "Broadband connection for cloud API access",
                      "Provided by runner"],
                 ],
                 widths=[1.5, 2.7, 2.3], font_size=10)
    caption(doc, "Table 4. Hardware specification")
    body(doc,
         "No graphics accelerator is required at any stage. The project performs "
         "no model training; where a language model is used, it is accessed as a "
         "hosted service over HTTPS.")

    h3(doc, "3.3.2 Software Specification")
    simple_table(doc,
                 ["Category", "Software and version"],
                 [
                     ["Operating System",
                      "Windows 11 (development); Ubuntu 22.04 LTS (CI runner)"],
                     ["Programming Languages",
                      "Python 3.11 or later; HCL2 (Terraform); JavaScript "
                      "(ES2020) for the dashboard"],
                     ["Development Environment",
                      "Visual Studio Code; Git 2.50; GitHub CLI"],
                     ["Libraries and Frameworks",
                      "PyYAML 6.0 (configuration and knowledge base); pytest 7.4 "
                      "(testing); React 18 (dashboard); Python standard library "
                      "http.server (dashboard backend)"],
                     ["Infrastructure as Code",
                      "Terraform 1.9 or later; AzureRM provider 4.x"],
                     ["CI/CD Platform",
                      "GitHub Actions with OIDC federated authentication"],
                     ["Cloud Platform",
                      "Microsoft Azure (validated); AWS and GCP supported by the "
                      "gate logic"],
                     ["Database",
                      "None required. State is held in Terraform remote state "
                      "(Azure Blob Storage); the knowledge base and policy are "
                      "version-controlled YAML files"],
                     ["Security Tools",
                      "Microsoft Entra ID workload identity federation; Azure "
                      "RBAC; GitHub code scanning (SARIF ingestion)"],
                     ["Optional Model Endpoint",
                      "Azure OpenAI (gpt-4o-mini) or Anthropic Messages API - "
                      "disabled by default"],
                 ],
                 widths=[1.7, 4.8], font_size=10)
    caption(doc, "Table 5. Software specification")

    page_break(doc)

    # ================= 4. DESIGN APPROACH AND DETAILS =================
    h1(doc, "4. Design Approach and Details")

    h2(doc, "4.1 System Architecture")
    body(doc,
         "The agent is positioned at a single, deliberately chosen point in the "
         "delivery lifecycle: after terraform plan has resolved the complete set "
         "of intended changes, and before terraform apply creates anything. This "
         "is the earliest moment at which the fully evaluated configuration is "
         "known, and the last moment at which nothing has yet been provisioned. "
         "Figure 2 shows the resulting architecture.")

    figure(doc, "fig2_architecture.png",
           "Fig. 3. System architecture of Agent SecOps", width_in=6.3)

    body(doc,
         "A developer commits Terraform configuration and opens a pull request. "
         "The workflow executes terraform plan and converts the resulting plan to "
         "JSON. That document, rather than the HCL source, is the input to the "
         "gate - an important distinction, because variables, modules, count and "
         "for_each expressions are already resolved at this stage, so the gate "
         "evaluates what will actually be created rather than what the source "
         "appears to declare.")
    body(doc,
         "Evaluation then proceeds through four stages.")

    bullet(doc, "The parser converts each entry of the plan's resource_changes "
                "array into a Resource object carrying a canonical Kind. "
                "Provider-specific types collapse onto shared abstractions, so "
                "azurerm_storage_account, aws_s3_bucket and google_storage_bucket "
                "all resolve to OBJECT_STORAGE. This single mapping is what makes "
                "the gate cloud-agnostic.",
           bold_lead="Layer 0 - Normalisation. ")
    bullet(doc, "Twenty-two rules, each an independently registered unit "
                "declaring its pillar, severity, applicable kinds and framework "
                "rationale, evaluate every mutating resource. Findings from this "
                "layer carry a confidence of 1.0 by construction and are the only "
                "findings permitted to block a deployment by default.",
           bold_lead="Layer 1 - Deterministic rules. ")
    bullet(doc, "For each resource, the pillars and watch-points indexed against "
                "its canonical kind are retrieved from the knowledge base and "
                "supplied, together with the findings already produced by Layer 1, "
                "to a reasoner. The reasoner reports only concerns that framework "
                "guidance implies but that no rule encodes. Retrieval is keyed on "
                "the type system rather than on embedding similarity, so the "
                "guidance applied to any resource is deterministic and auditable.",
           bold_lead="Layer 2 - Framework reasoning. ")
    bullet(doc, "Severity thresholds, rule overrides and time-boxed waivers are "
                "applied, and the surviving findings are aggregated into a single "
                "verdict, which is surfaced to the pipeline as an exit code.",
           bold_lead="Layer 3 - Organisational policy. ")

    body(doc,
         "Two reasoner implementations satisfy the same interface. An offline "
         "reasoner applies deterministic heuristics corresponding to the "
         "knowledge base watch-points; it is free, runs in milliseconds, is the "
         "default in continuous integration, and serves as the experimental "
         "control against which the language-model reasoner is measured. The "
         "model-backed reasoner communicates with Azure OpenAI or the Anthropic "
         "API and is constrained by resource caps, prompt redaction and a content "
         "-addressed response cache. If no endpoint is configured, the factory "
         "silently falls back to the offline reasoner, so the gate never fails "
         "because a model is unreachable.")

    figure(doc, "fig3_gate_output.png",
           "Fig. 4. Gate verdict produced for a plan containing seeded "
           "misconfigurations", width_in=6.3)

    h2(doc, "4.2 Design")

    h3(doc, "4.2.1 Data Flow Diagram")
    body(doc,
         "Figure 4 presents the data flow. The Terraform plan JSON enters the "
         "parser, which emits normalised resources into the rule engine and the "
         "reasoner. The knowledge base acts as a reference data store consulted "
         "during retrieval, and the policy file as a reference store consulted "
         "during verdict aggregation. Findings converge on the verdict engine, "
         "which emits the report artefacts and the exit code that the pipeline "
         "consumes.")

    figure(doc, "fig4_dfd.png", "Fig. 5. Data flow diagram (Level 1)",
           width_in=6.3)

    h3(doc, "4.2.2 Use Case Diagram")
    body(doc,
         "Four actors interact with the system. The Developer commits "
         "infrastructure changes and reads the resulting compliance report. The "
         "CI/CD Pipeline invokes the gate and acts on its exit code. The Platform "
         "Engineer maintains organisational policy, including thresholds, rule "
         "overrides and waivers. The Reasoning Service is an external supporting "
         "actor consulted only when the model-backed reasoner is enabled. "
         "Principal use cases comprise evaluating a plan, producing a verdict, "
         "publishing a report, gating the deployment, configuring policy, "
         "granting a time-boxed waiver, and reviewing benchmark results.")

    figure(doc, "fig5_usecase.png", "Fig. 6. Use case diagram", width_in=6.1)

    h3(doc, "4.2.3 Class Diagram")
    body(doc,
         "The domain model is compact. Resource, Finding, PlanSummary and "
         "GateResult constitute the data model, supported by the enumerations "
         "Provider, Kind, Action, Severity, Verdict and Pillar. Rule is an "
         "abstract base class from which every concrete CAF and WAF rule derives, "
         "each contributing its metadata and a check method. Reasoner is a "
         "parallel abstraction realised by OfflineReasoner and LLMReasoner. "
         "Policy and Waiver express organisational configuration. The engine "
         "module composes these into the evaluation pipeline, and the report "
         "module renders GateResult into its three output formats.")

    figure(doc, "fig6_class.png",
           "Fig. 7. Class diagram of the core domain model", width_in=6.3)

    h3(doc, "4.2.4 Sequence Diagram")
    body(doc,
         "For a single pull request the interaction proceeds as follows. GitHub "
         "Actions invokes terraform plan and terraform show, then calls the agent "
         "command-line interface with the resulting plan file. The engine loads "
         "policy, invokes the parser, iterates the rule registry over each "
         "mutating resource, passes the resources and existing findings to the "
         "reasoner, applies waivers and thresholds, and returns a verdict. The "
         "CLI renders the reports, writes the GitHub outputs and terminates with "
         "the verdict exit code. The workflow then either publishes the report and "
         "halts, or proceeds to terraform apply.")

    figure(doc, "fig7_sequence.png",
           "Fig. 8. Sequence diagram for a single pipeline run", width_in=6.3)

    page_break(doc)

    # ================= 5. REFERENCES =================
    h1(doc, "5. References")

    para(doc, "Journals and Conferences: <IEEE Format>", size=12, bold=True,
         spacing=1.15, space_after=8)

    refs = [
        "A. Rahman, C. Parnin, and L. Williams, \"The seven sins: Security smells "
        "in infrastructure as code scripts,\" in Proc. IEEE/ACM 41st Int. Conf. "
        "Software Engineering (ICSE), Montreal, QC, Canada, 2019, pp. 164-175.",

        "A. Rahman, M. R. Rahman, C. Parnin, and L. Williams, \"Security smells "
        "in Ansible and Chef scripts: A replication study,\" ACM Trans. Software "
        "Engineering and Methodology, vol. 30, no. 1, pp. 1-31, 2021.",

        "M. Guerriero, M. Garriga, D. A. Tamburri, and F. Palomba, \"Adoption, "
        "support, and challenges of infrastructure-as-code: Insights from "
        "industry,\" in Proc. IEEE Int. Conf. Software Maintenance and Evolution "
        "(ICSME), Cleveland, OH, USA, 2019, pp. 580-589.",

        "F. A. Bhuiyan and A. Rahman, \"Characterizing co-located insecure coding "
        "patterns in infrastructure as code scripts,\" in Proc. 35th IEEE/ACM "
        "Int. Conf. Automated Software Engineering Workshops (ASEW), 2020, "
        "pp. 27-32.",

        "R. Opdebeeck, A. Zerouali, and C. De Roover, \"Smelly variables in "
        "Ansible infrastructure code: Detection, prevalence, and lifetime,\" in "
        "Proc. 19th Int. Conf. Mining Software Repositories (MSR), 2022, "
        "pp. 61-72.",

        "N. Saavedra and J. F. Ferreira, \"GLITCH: Automated polyglot security "
        "smell detection in infrastructure as code,\" in Proc. 37th IEEE/ACM Int. "
        "Conf. Automated Software Engineering (ASE), 2022, pp. 1-12.",

        "M. Chiari, M. De Pascalis, and M. Pradella, \"Static analysis of "
        "infrastructure as code: A survey,\" in Proc. IEEE 19th Int. Conf. "
        "Software Architecture Companion (ICSA-C), 2022, pp. 218-225.",

        "J. Sandobalin, E. Insfran, and S. Abrahao, \"On the effectiveness of "
        "tools to support infrastructure as code: Model-driven versus "
        "code-centric,\" IEEE Access, vol. 8, pp. 17734-17761, 2020.",

        "M. Chen et al., \"Evaluating large language models trained on code,\" "
        "arXiv preprint arXiv:2107.03374, 2021.",

        "T. B. Brown et al., \"Language models are few-shot learners,\" in Proc. "
        "Advances in Neural Information Processing Systems (NeurIPS), vol. 33, "
        "2020, pp. 1877-1901.",

        "P. Lewis et al., \"Retrieval-augmented generation for "
        "knowledge-intensive NLP tasks,\" in Proc. Advances in Neural Information "
        "Processing Systems (NeurIPS), vol. 33, 2020, pp. 9459-9474.",

        "T. Sandall and various contributors, \"Open Policy Agent: An open source, "
        "general-purpose policy engine,\" Cloud Native Computing Foundation, "
        "Technical Documentation, 2023.",

        "HashiCorp, \"Sentinel: Policy as code framework,\" HashiCorp Technical "
        "Documentation, 2024.",

        "H. Pearce, B. Ahmad, B. Tan, B. Dolan-Gavitt, and R. Karri, \"Asleep at "
        "the keyboard? Assessing the security of GitHub Copilot's code "
        "contributions,\" in Proc. IEEE Symp. Security and Privacy (S&P), 2022, "
        "pp. 754-768.",

        "E. Malul, Y. Meidan, D. Mimran, Y. Elovici, and A. Shabtai, "
        "\"GenKubeSec: LLM-based Kubernetes misconfiguration detection, "
        "localization, reasoning, and remediation,\" arXiv preprint "
        "arXiv:2405.19954, 2024.",

        "Q.-H. Vo, H. Dao, and K. Fukuda, \"Harnessing the power of LLMs for code "
        "smell detection in Terraform infrastructure as code,\" in Proc. IEEE 49th "
        "Annu. Computers, Software, and Applications Conf. (COMPSAC), 2025, "
        "pp. 533-542.",
    ]
    for i, r in enumerate(refs, 1):
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.line_spacing = 1.15
        pf.space_after = Pt(6)
        pf.left_indent = Inches(0.4)
        pf.first_line_indent = Inches(-0.4)
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        _set_run(p.add_run(f"[{i}] "), 12)
        _set_run(p.add_run(r), 12)

    para(doc, "", space_after=4)
    para(doc, "Weblinks:", size=12, bold=True, spacing=1.15,
         space_before=8, space_after=6)

    links = [
        "Microsoft, \"Microsoft Cloud Adoption Framework for Azure,\" "
        "https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/",
        "Microsoft, \"Azure Well-Architected Framework,\" "
        "https://learn.microsoft.com/en-us/azure/well-architected/",
        "HashiCorp, \"Terraform JSON output format,\" "
        "https://developer.hashicorp.com/terraform/internals/json-format",
        "GitHub, \"Configuring OpenID Connect in Azure,\" "
        "https://docs.github.com/en/actions/deployment/security-hardening-your-"
        "deployments/configuring-openid-connect-in-azure",
        "Prisma Cloud, \"Checkov: Policy-as-code for infrastructure,\" "
        "https://www.checkov.io/",
        "OASIS, \"Static Analysis Results Interchange Format (SARIF) Version "
        "2.1.0,\" https://docs.oasis-open.org/sarif/sarif/v2.1.0/",
    ]
    for i, l in enumerate(links, 1):
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.line_spacing = 1.15
        pf.space_after = Pt(5)
        pf.left_indent = Inches(0.4)
        pf.first_line_indent = Inches(-0.4)
        _set_run(p.add_run(f"[W{i}] "), 12)
        _set_run(p.add_run(l), 12)

    doc.save(OUTPUT)
    print(f"Written: {OUTPUT}")


if __name__ == "__main__":
    build()
