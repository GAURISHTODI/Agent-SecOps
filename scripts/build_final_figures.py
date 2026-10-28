"""Figures for the final-review deck: where the agent sits, the current
architecture (Step 0, Layers 1, 2a, 2b, 3) and the gate algorithm as a
flowchart.

Uses the drawing helpers and palette of build_figures.py so every figure in
the project shares one style.

Run:  python scripts/build_final_figures.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from matplotlib.patches import FancyBboxPatch, Polygon  # noqa: E402

from scripts.build_figures import (  # noqa: E402
    BLUE, CRIT, FILL_BLUE, FILL_GREEN, FILL_GREY, FILL_ORANGE, FILL_RED, GOOD,
    INK, INK2, MUTED, ORANGE, WARN, _save, arrow, blank_ax, box, label,
)

FILL_WARN = "#fdf1d6"
PURPLE = "#7a4fc9"
FILL_PURPLE = "#ece4fa"


def container(ax, x, y, w, h, edge, fill, lw=1.6):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                                boxstyle="round,pad=0.004,rounding_size=0.02",
                                linewidth=lw, edgecolor=edge, facecolor=fill, zorder=1))


def diamond(ax, cx, cy, w, h, text, fontsize=8.4):
    ax.add_patch(Polygon([(cx, cy + h / 2), (cx + w / 2, cy), (cx, cy - h / 2), (cx - w / 2, cy)],
                         closed=True, facecolor=FILL_WARN, edgecolor=WARN, linewidth=1.2, zorder=3))
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fontsize, color=INK,
            fontweight="bold", zorder=5, linespacing=1.3)


# ----------------------------------------------------------------------
# Where the agent sits
# ----------------------------------------------------------------------

def fig_where_agent_sits():
    fig, ax = blank_ax(12.5, 5.6)

    stages = [
        (1, "Write\nTerraform", FILL_GREY, MUTED),
        (17.5, "Commit /\npull request", FILL_GREY, MUTED),
        (34, "terraform plan\n+ show -json", FILL_GREY, MUTED),
        (50.5, "AGENT SECOPS\nGATE", FILL_BLUE, BLUE),
        (67, "terraform\napply", FILL_GREY, MUTED),
        (83.5, "Running in\nAzure / AWS / GCP", FILL_GREY, MUTED),
    ]
    for x, text, fill, edge in stages:
        box(ax, x, 74, 15.5, 13, text, fill, edge, 9.5, True,
            text_color=BLUE if edge == BLUE else INK)
    for x in (16.5, 33, 49.5, 66, 82.5):
        arrow(ax, (x, 80.5), (x + 1, 80.5), lw=1.6)
    ax.add_patch(FancyBboxPatch((49.6, 72.6), 17.3, 15.8,
                                boxstyle="round,pad=0.004,rounding_size=0.03",
                                linewidth=2.2, edgecolor=BLUE, facecolor="none",
                                linestyle="--", zorder=2))

    # before / after: does the resource exist yet?
    ax.plot([1, 66.2], [70, 70], color=GOOD, lw=2.2)
    label(ax, 33.6, 66.5, "nothing exists yet: a mistake costs nothing to fix", 9, GOOD, weight="bold")
    ax.plot([67, 99], [70, 70], color=CRIT, lw=2.2)
    label(ax, 83, 66.5, "resource exists: exposure and bills have started", 9, CRIT, weight="bold")

    label(ax, 50, 58.5, "What checks the infrastructure at each point", 10, INK, weight="bold")
    tools = [
        (1, "IDE linters\n(tflint)\n\nsyntax and style", FILL_GREY, MUTED),
        (17.5, "Checkov / tfsec\n\nfixed rules on\nthe .tf source,\none file at a time", FILL_GREY, MUTED),
        (34, "(no check:\nthe plan is just\nprinted)", "#ffffff", MUTED),
        (50.5, "Judges the exact\nplanned change:\nCAF/WAF rules,\npolicies, graph risk\nacross resources", FILL_BLUE, BLUE),
        (67, "(no check:\napply just runs)", "#ffffff", MUTED),
        (83.5, "Azure Policy /\nDefender for Cloud\n\nafter the resource\nexists and bills", FILL_RED, CRIT),
    ]
    for x, text, fill, edge in tools:
        box(ax, x, 27, 15.5, 27, text, fill, edge, 8.6,
            text_color=BLUE if edge == BLUE else INK)

    box(ax, 40, 3, 21, 12, "BLOCK  (exit 2)\nreport on the PR,\nnothing is created", FILL_RED, CRIT, 8.6, True)
    box(ax, 63, 3, 21, 12, "PASS  (exit 0)\napply may run", FILL_GREEN, GOOD, 8.6, True)
    arrow(ax, (55, 27), (52, 15.4), color=CRIT, lw=1.4)
    arrow(ax, (62, 27), (71, 15.4), color=GOOD, lw=1.4)
    return _save(fig, "final_where_agent_sits.png")


# ----------------------------------------------------------------------
# Architecture with the current layer names
# ----------------------------------------------------------------------

def fig_architecture_v2():
    fig, ax = blank_ax(11.5, 7.2)

    box(ax, 2, 87, 19, 10, "Developer\ncommits .tf", FILL_GREY, MUTED, 9, True)
    box(ax, 27, 87, 19, 10, "GitHub Actions\npull request", FILL_GREY, MUTED, 9, True)
    box(ax, 52, 87, 19, 10, "terraform plan\n+ show -json", FILL_GREY, MUTED, 9, True)
    box(ax, 77, 87, 21, 10, "plan.json\nresources + config", FILL_GREY, MUTED, 9, True)
    for x in (21, 46, 71):
        arrow(ax, (x, 92), (x + 6, 92))

    container(ax, 2, 22, 96, 59, BLUE, "#f5f9fe")
    label(ax, 50, 78, "AGENT SECOPS  -  CAF / WAF COMPLIANCE GATE", 10.5, BLUE, weight="bold")
    arrow(ax, (87.5, 87), (87.5, 81.2), color=BLUE, lw=1.4)

    box(ax, 6, 64, 88, 10,
        "Step 0  -  Read the plan:  provider types -> cloud-neutral kinds  |  fold helper resources onto their owner\n"
        "(S3 ACL / versioning -> bucket)  |  build the dependency graph from references, across modules",
        FILL_GREY, MUTED, 8.4)

    box(ax, 6, 40.5, 27, 19,
        "Layer 1\nDeterministic rules\n\n22 CAF/WAF checks,\nconfidence 1.0",
        FILL_BLUE, BLUE, 8.6, True)
    box(ax, 36.5, 40.5, 27, 19,
        "Layer 2a\nOrganisational\ncustomized policies\n\n12 checks from the\nCAF/WAF knowledge base",
        FILL_ORANGE, ORANGE, 8.4, True)
    box(ax, 67, 40.5, 27, 19,
        "Layer 2b\nDependency-graph risk\n\nexposure x weakness x value,\nusing Layer-1 findings;\nreported if the link adds risk",
        FILL_PURPLE, PURPLE, 8.2, True)
    for x, c in ((19.5, BLUE), (50, ORANGE), (80.5, PURPLE)):
        arrow(ax, (x, 64), (x, 59.8), color=c)

    box(ax, 6, 26, 88, 10,
        "Layer 3  -  Thresholds & waivers  (policies/policy.yaml):  rule finding >= high -> BLOCK  |  >= medium -> REMEDIATE\n"
        "time-boxed waivers  |  per-rule overrides  |  layer-2 findings advisory unless the policy trusts them",
        FILL_GREY, MUTED, 8.4)
    for x in (19.5, 50, 80.5):
        arrow(ax, (x, 40.5), (x, 36.3), color=MUTED)

    box(ax, 4, 4, 22, 12, "BLOCK  (exit 2)\npipeline stops,\nnothing is created", FILL_RED, CRIT, 8.6, True)
    box(ax, 28.5, 4, 22, 12, "REMEDIATE  (exit 1)\nwarning, fix\nfollow-up", FILL_WARN, WARN, 8.6, True)
    box(ax, 53, 4, 22, 12, "PASS  (exit 0)\nterraform apply\nmay proceed", FILL_GREEN, GOOD, 8.6, True)
    box(ax, 77.5, 4, 20.5, 12, "Reports\nPR comment | JSON\nSARIF | PDF | dashboard", FILL_GREY, MUTED, 8.4, True)
    for x in (15, 39.5, 64):
        arrow(ax, (50, 26), (x, 16.3), color=INK2, lw=1.1)
    arrow(ax, (87.75, 26), (87.75, 16.3), color=INK2, lw=1.1)
    return _save(fig, "final_architecture.png")


# ----------------------------------------------------------------------
# The algorithm as a flowchart
# ----------------------------------------------------------------------

def fig_flowchart():
    """Three rows read as a snake: left to right, right to left, left to right."""
    fig, ax = blank_ax(12.5, 7.4)

    # row 1: reading the plan and Layer 1 (left to right)
    box(ax, 1, 78, 15, 12, "Start\nplan.json", FILL_GREY, MUTED, 9, True)
    diamond(ax, 28, 84, 17, 15, "Valid plan\nJSON?")
    box(ax, 41, 76, 24, 16, "Step 0: read the plan\nnormalise kinds, fold helper\nresources, build the graph",
        FILL_GREY, MUTED, 8.4)
    box(ax, 72, 76, 26, 16, "Layer 1: run the 22\ndeterministic rules on\nevery resource",
        FILL_BLUE, BLUE, 8.6, True)
    box(ax, 1, 60, 15, 8, "Exit 3 (error)", FILL_RED, CRIT, 8.6, True)
    arrow(ax, (16, 84), (19.5, 84))
    arrow(ax, (36.5, 84), (41, 84))
    label(ax, 38.8, 86.5, "yes", 8, GOOD, weight="bold")
    arrow(ax, (65, 84), (72, 84))
    arrow(ax, (28, 76.5), (16.3, 66), color=CRIT)
    label(ax, 18.5, 73, "no", 8, CRIT, weight="bold")

    # row 2: the reasoning layer (right to left), an optional group
    container(ax, 22, 40, 77, 30, ORANGE, "#fffaf6", lw=1.3)
    label(ax, 60.5, 66.5, "Reasoning layer  (when switched off, findings go straight to Layer 3)",
          8.4, ORANGE, weight="bold")
    box(ax, 66, 43, 30, 19, "Layer 2a: organisational\ncustomized policies\n\nlook up the pillars for each kind,\nrun matching checks, skip duplicates",
        FILL_ORANGE, ORANGE, 8.2)
    box(ax, 26, 43, 33, 19, "Layer 2b: dependency-graph risk\n\nspread exposure along links (x0.75\nper hop, max 3 hops); report if risk\n>= 0.35 and the link adds >= 0.10",
        FILL_PURPLE, PURPLE, 8.2)
    arrow(ax, (85, 76), (85, 62.4), color=ORANGE, lw=1.4)
    arrow(ax, (66, 52.5), (59.3, 52.5), color=ORANGE, lw=1.4)

    # row 3: Layer 3 (left to right)
    label(ax, 47, 35.5, "Layer 3: thresholds & waivers", 9.5, INK, weight="bold", ha="left")
    box(ax, 4, 17, 18, 13, "Apply waivers\n(accepted risks\nset aside)", FILL_GREY, MUTED, 8.4)
    diamond(ax, 37, 23.5, 19, 15, "Rule finding\n>= high?")
    diamond(ax, 62, 23.5, 19, 15, "Any finding\n>= medium?")
    box(ax, 80, 18, 18, 11, "PASS  (exit 0)\napply may run", FILL_GREEN, GOOD, 8.6, True)
    box(ax, 28, 1, 18, 9, "BLOCK  (exit 2)", FILL_RED, CRIT, 8.6, True)
    box(ax, 53, 1, 18, 9, "REMEDIATE  (exit 1)", FILL_WARN, WARN, 8.6, True)
    box(ax, 77, 1, 22, 11, "Every verdict writes:\nPR comment, JSON,\nSARIF, PDF", FILL_GREY, MUTED, 8.2)
    arrow(ax, (42.5, 43), (13, 30.3), color=PURPLE, lw=1.4)
    arrow(ax, (22, 23.5), (27.5, 23.5))
    arrow(ax, (46.5, 23.5), (52.5, 23.5))
    label(ax, 49.5, 26, "no", 8, GOOD, weight="bold")
    arrow(ax, (71.5, 23.5), (80, 23.5))
    label(ax, 75.5, 26, "no", 8, GOOD, weight="bold")
    arrow(ax, (37, 16), (37, 10.3), color=CRIT)
    label(ax, 39.5, 13, "yes", 8, CRIT, weight="bold", ha="left")
    arrow(ax, (62, 16), (62, 10.3), color=WARN)
    label(ax, 64.5, 13, "yes", 8, WARN, weight="bold", ha="left")
    return _save(fig, "final_flowchart.png")


def main():
    fig_where_agent_sits()
    fig_architecture_v2()
    fig_flowchart()


if __name__ == "__main__":
    main()
