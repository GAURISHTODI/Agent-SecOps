"""Fill the Review-2 PPT template in place for Agent SecOps.

The template is edited rather than recreated, so the VIT branding, slide
master, layouts, SDG icons and footer placeholders are all preserved
exactly as supplied. Only the text of the content placeholders changes.

Run:  python scripts/build_ppt.py
"""
from __future__ import annotations

import copy
from pathlib import Path

from pptx import Presentation
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "4 Review 2 PPT Template.pptx"
OUTPUT = ROOT / "Agent SecOps - Review 2 Presentation.pptx"
FIGDIR = ROOT / "docs" / "figures"

TITLE = "AGENT SECOPS: AN AI-DRIVEN SECOPS AGENT FOR CAF/WAF-ALIGNED INFRASTRUCTURE-AS-CODE PIPELINES"
COURSE = "B.Tech / BCSE497J - Project-I"


def set_text(shape, lines, size=18, bullet_sizes=None):
    """Replace a shape's text with `lines`, keeping its existing styling."""
    tf = shape.text_frame
    tf.clear()
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        if isinstance(line, tuple):
            text, level = line
        else:
            text, level = line, 0
        p.level = level
        run = p.add_run()
        run.text = text
        sz = size
        if bullet_sizes and i < len(bullet_sizes):
            sz = bullet_sizes[i]
        run.font.size = Pt(sz if level == 0 else max(sz - 2, 11))
    return tf


def find(slide, *names):
    for sh in slide.shapes:
        if sh.name in names:
            return sh
    return None


def by_title(slide):
    """Return the shape holding the slide's section heading."""
    return find(slide, "object 2", "Title 1", "Title 6")


def content_of(slide, prs=None):
    """Return the slide's text content placeholder.

    Some slides use their content placeholder for a picture instead of
    text (the Literature Review slide does). In that case a text box is
    added over the content area rather than mangling the picture.
    """
    for sh in slide.shapes:
        if sh.name.startswith("Content Placeholder") and sh.has_text_frame:
            return sh
    for sh in slide.shapes:
        if sh.has_text_frame and sh.name not in ("object 2", "Title 1", "Title 6") \
                and not sh.name.startswith(("Date", "Footer", "Slide Number")):
            return sh
    if prs is not None:
        from pptx.util import Inches
        box = slide.shapes.add_textbox(
            Inches(0.7), Inches(1.6), prs.slide_width - Inches(1.4), Inches(4.6)
        )
        box.text_frame.word_wrap = True
        return box
    return None


def add_figure(prs, slide, filename, top_in, height_in):
    """Centre a generated figure on the slide beneath the text block."""
    path = FIGDIR / filename
    if not path.exists():
        return None
    from PIL import Image  # noqa: F401  (optional, only for aspect ratio)
    pic = slide.shapes.add_picture(str(path), Inches(0), Inches(top_in),
                                   height=Inches(height_in))
    pic.left = int((prs.slide_width - pic.width) / 2)
    return pic


def shrink(prs, shape, top_in, height_in):
    """Constrain a text placeholder so a figure fits below it.

    All four geometry values must be set together: writing only top and
    height leaves the placeholder with a zero left/width, which
    PowerPoint renders as an invisible sliver.
    """
    shape.left = Inches(0.55)
    shape.width = prs.slide_width - Inches(1.1)
    shape.top = Inches(top_in)
    shape.height = Inches(height_in)


def duplicate_slide(prs, index):
    """Clone slide at `index` and append it, preserving layout and shapes."""
    source = prs.slides[index]
    dest = prs.slides.add_slide(source.slide_layout)
    for shp in list(dest.shapes):
        shp._element.getparent().remove(shp._element)
    for shp in source.shapes:
        dest.shapes._spTree.append(copy.deepcopy(shp._element))
    return dest


def build() -> None:
    prs = Presentation(TEMPLATE)
    s = prs.slides

    # ---------------- Slide 1 - title ----------------
    t = find(s[0], "Title 6")
    if t:
        set_text(t, [COURSE, TITLE], size=22, bullet_sizes=[18, 24])
    obj = find(s[0], "object 3")
    if obj:
        set_text(obj, [
            "Team members:",
            "Bhumika Singh          (23BCE0196)",
            "Akshat Gupta            (23BCE0958)",
            "Gaurish Todi             (23BCI0262)",
            "",
            "Faculty guide :",
            "Dr. S. M. Farooq",
        ], size=16)

    # ---------------- Slide 2 - approval mail (left as-is) ------------
    # This slide carries the guide's approval screenshot; content is the
    # team's to paste in, so only the instruction line is softened.
    c = content_of(s[1])
    if c:
        set_text(c, [
            "Approval obtained from the project guide for the title, "
            "objectives, scope and expected outcome.",
            "[Paste the approval e-mail screenshot here]",
        ], size=16)

    # ---------------- Slide 3 - Aim ----------------
    set_text(content_of(s[2]), [
        "To design and implement an AI-driven SecOps agent that sits between "
        "Terraform plan generation and CI/CD deployment, and automatically "
        "checks every proposed cloud resource against Microsoft's Cloud "
        "Adoption Framework (CAF) and Well-Architected Framework (WAF) before "
        "the pipeline is permitted to proceed to deployment on Azure, AWS or GCP.",
    ], size=20)

    # ---------------- Slide 4 - Abstract ----------------
    set_text(content_of(s[3]), [
        "Cloud teams ship infrastructure using Terraform through CI/CD "
        "pipelines into Azure, AWS and GCP.",
        "Providers publish CAF and WAF as narrative documentation, not "
        "enforceable code, so it is rarely checked automatically before "
        "deployment.",
        "Existing tools (Checkov, OPA, Sentinel) catch only violations of rules "
        "someone already wrote; they cannot reason about framework intent.",
        "Agent SecOps places an AI agent between terraform plan and terraform "
        "apply. It reads the plan JSON, evaluates it against CAF/WAF using a "
        "policy-aware reasoning layer, and returns pass, block or remediate "
        "with a plain-language justification.",
        "Non-compliant infrastructure is stopped before it is ever applied to "
        "the cloud - before cost is incurred or exposure occurs.",
    ], size=15)

    # ---------------- Slide 5 - Literature Review ----------------
    c = content_of(s[4], prs)
    if c:
        set_text(c, [
            "IaC defect studies - Rahman et al. (ICSE'19) identified seven "
            "recurring security smells in IaC; replicated across Ansible/Chef "
            "(TOSEM'21). GLITCH (ASE'22) showed one normalised representation "
            "can serve many IaC technologies.",
            "Policy-as-code tooling - Chiari et al. (ICSA-C'22) surveyed static "
            "IaC analysis: almost all production tooling is rule-based, i.e. "
            "correctness is an explicit hand-written predicate.",
            "LLMs for code security - Lewis et al. introduced RAG; Pearce et al. "
            "(S&P'22) showed model-generated code is not automatically secure - "
            "motivating our advisory-by-default design.",
            "Closest prior work - GenKubeSec (2024) for Kubernetes and Vo et al. "
            "(COMPSAC'25) for Terraform show LLMs out-detect rule-based scanners, "
            "but both analyse static artefacts, not an enforcing pipeline gate.",
        ], size=13)

    # ---------------- Slide 6 - Research Gap ----------------
    set_text(content_of(s[5]), [
        "Rule-bound detection - static tools detect only violations of rules "
        "already hand-authored; uncodified framework guidance is invisible, and "
        "rule sets must be maintained per cloud provider.",
        "Analysis without enforcement - recent LLM work (GenKubeSec; Vo et al. "
        "2025) analyses static artefacts, but is not embedded as an enforcing "
        "control inside a CI/CD pipeline.",
        "No framework grounding - no existing study maps findings to the "
        "specific pillars of Microsoft's CAF and WAF.",
        "Single-cloud scope - no demonstrated gate normalises Azure, AWS and GCP "
        "so that one rule serves all three.",
        "This project addresses all four gaps simultaneously.",
    ], size=14)

    # ---------------- Slide 7 - Objectives ----------------
    set_text(content_of(s[6]), [
        "O1 - Parse Terraform plan JSON and evaluate every resource against CAF "
        "governance areas and the six WAF pillars.",
        "O2 - Normalise Azure, AWS and GCP resource types into canonical kinds "
        "so gate logic stays cloud-agnostic.",
        "O3 - Implement a policy-aware reasoning layer that reports violations "
        "of framework intent no rule encodes.",
        "O4 - Integrate as an enforcing GitHub Actions gate: apply is "
        "unreachable on a block verdict.",
        "O5 - Quantify detection rate, false positives and the marginal gain of "
        "reasoning over rules alone.",
        "O6 - Validate against a live Azure subscription at negligible cost.",
    ], size=13)

    # ---------------- Slide 8 - Architecture ----------------
    c8 = content_of(s[7])
    set_text(c8, [
        "Developer commits .tf  ->  GitHub Actions  ->  terraform plan  ->  "
        "plan.json",
        "Layer 0 - Normalisation: provider types collapse to canonical kinds "
        "(azurerm_storage_account / aws_s3_bucket / google_storage_bucket -> "
        "OBJECT_STORAGE).",
        "Layer 1 - Deterministic rules: 22 CAF/WAF checks, confidence 1.0; only "
        "these may block by default.",
        "Layer 2 - Framework reasoning: retrieves pillar guidance indexed by "
        "resource kind; reports intent violations no rule encodes.",
        "Layer 3 - Policy: severity thresholds, rule overrides, expiring waivers.",
        "BLOCK -> pipeline halts, report posted to PR, nothing deployed.   "
        "PASS -> terraform apply proceeds to Azure / AWS / GCP.",
    ], size=11)
    shrink(prs, c8, 1.25, 1.80)
    add_figure(prs, s[7], "fig2_architecture.png", top_in=3.15,
               height_in=3.62)

    # ---------------- Slide 9 - Functional Requirements ----------------
    set_text(content_of(s[8]), [
        "FR1 Plan ingestion - accept terraform show -json output; reject "
        "malformed input with an actionable message.",
        "FR2 Normalisation - map Azure/AWS/GCP types to canonical kinds; handle "
        "create, update, replace, delete.",
        "FR3 Deterministic evaluation - 22 rules, each returning rule id, "
        "pillar, severity, explanation and remediation.",
        "FR4 Framework reasoning - retrieve relevant guidance; never duplicate a "
        "rule finding.",
        "FR5 Policy - severity thresholds, rule overrides, time-boxed waivers "
        "from external configuration.",
        "FR6 Verdict - aggregate to pass / remediate / block, exposed as a "
        "process exit code (0 / 1 / 2).",
        "FR7 Reporting - Markdown for the PR, JSON for machines, SARIF 2.1.0 for "
        "the Security tab.",
        "FR8 Pipeline integration - gate positioned between plan and apply; "
        "blocks apply on a block verdict.",
    ], size=12)

    # ---------------- Slide 10 - Modules ----------------
    set_text(content_of(s[9]), [
        "M1 Plan parser and data model - agent/plan_parser.py, agent/models.py "
        "(Akshat Gupta)",
        "M2 Deterministic rule engine - agent/rules/ : 7 CAF + 15 WAF rules "
        "(Akshat Gupta)",
        "M3 Knowledge base and reasoning layer - agent/knowledge/caf_waf_kb.yaml, "
        "agent/reasoner/ (Gaurish Todi)",
        "M4 Orchestration and policy engine - agent/engine.py, agent/config.py "
        "(Gaurish Todi)",
        "M5 Evaluation harness and dashboard - scripts/benchmark.py, dashboard/ "
        "(Gaurish Todi)",
        "M6 Reporting and CLI - agent/report.py, agent/cli.py (Bhumika Singh)",
        "M7 CI/CD pipeline and cloud infrastructure - "
        ".github/workflows/secops-gate.yml, infra/demo/, scripts/azure-*.sh "
        "(Bhumika Singh)",
    ], size=13)

    # ---------------- Slide 11 - Experiments and Results ----------------
    c11 = content_of(s[10])
    set_text(c11, [
        "Test set: 42 hand-labelled seeded violations across Azure, AWS and GCP, "
        "plus a compliant module as the false-positive control.",
        "Deterministic rules alone: 37 / 42 detected (88.1%) - approximately what "
        "a static scanner provides.",
        "Rules + reasoning layer: 42 / 42 detected (100%).",
        "Marginal contribution of reasoning: 5 violations recoverable only by "
        "reasoning over framework guidance - the core research claim, quantified.",
        "False positives on the compliant module: 0.  Median gate latency: under "
        "10 ms.  Automated tests: 63 passing.",
        "Live validation: gated and approved a real Azure deployment of 4 "
        "resources; steady-state cost approximately Rs. 4 per month.",
    ], size=11)
    shrink(prs, c11, 1.25, 2.30)
    add_figure(prs, s[10], "fig8_benchmark.png", top_in=3.68,
               height_in=3.10)

    # ---------------- Slide 12 - Conclusion ----------------
    set_text(content_of(s[11]), [
        "A working proof-of-concept gate now intercepts real Terraform plans "
        "inside GitHub Actions and returns pass / remediate / block against CAF "
        "and WAF before any resource is created.",
        "The three-layer design keeps authority with deterministic rules while "
        "the reasoning layer widens coverage - measured at +5 violations with "
        "zero false positives.",
        "Cloud-agnosticism is demonstrated, not asserted: one rule set gates "
        "Azure, AWS and GCP plans, verified by automated test.",
        "Status advanced from TRL 3 (analytical proof of concept) to TRL 4 "
        "(component validation in a laboratory environment).",
        "Future work: replace self-authored ground truth with an independent "
        "corpus, measure LLM-reasoner precision at volume to justify enabling it "
        "as a blocking control, and deepen AWS and GCP rule content.",
    ], size=13)

    # ---------------- Slide 13 - References ----------------
    r = find(s[12], "Rectangle 3")
    if r:
        set_text(r, [
            "[1] A. Rahman, C. Parnin, and L. Williams, \"The seven sins: "
            "Security smells in infrastructure as code scripts,\" in Proc. "
            "IEEE/ACM ICSE, 2019, pp. 164-175.",
            "[2] N. Saavedra and J. F. Ferreira, \"GLITCH: Automated polyglot "
            "security smell detection in infrastructure as code,\" in Proc. "
            "IEEE/ACM ASE, 2022, pp. 1-12.",
            "[3] M. Chiari, M. De Pascalis, and M. Pradella, \"Static analysis of "
            "infrastructure as code: A survey,\" in Proc. IEEE ICSA-C, 2022, "
            "pp. 218-225.",
            "[4] P. Lewis et al., \"Retrieval-augmented generation for "
            "knowledge-intensive NLP tasks,\" in Proc. NeurIPS, vol. 33, 2020, "
            "pp. 9459-9474.",
            "[5] H. Pearce, B. Ahmad, B. Tan, B. Dolan-Gavitt, and R. Karri, "
            "\"Asleep at the keyboard? Assessing the security of GitHub Copilot's "
            "code contributions,\" in Proc. IEEE S&P, 2022, pp. 754-768.",
            "[6] E. Malul, Y. Meidan, D. Mimran, Y. Elovici, and A. Shabtai, "
            "\"GenKubeSec: LLM-based Kubernetes misconfiguration detection, "
            "localization, reasoning, and remediation,\" arXiv:2405.19954, 2024.",
            "[7] Q.-H. Vo, H. Dao, and K. Fukuda, \"Harnessing the power of LLMs "
            "for code smell detection in Terraform infrastructure as code,\" in "
            "Proc. IEEE COMPSAC, 2025, pp. 533-542.",
        ], size=11)

    prs.save(OUTPUT)
    print(f"Written: {OUTPUT}")


if __name__ == "__main__":
    build()
