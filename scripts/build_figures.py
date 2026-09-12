"""Generate every figure used in the Project-I report and the Review-2 deck.

All diagrams are drawn programmatically so they can be regenerated after any
design change, and so the report never depends on a hand-drawn asset.

Chart colours follow the project's validated data-visualisation palette:
    series 1 (identity A) #2a78d6      series 2 (identity B) #eb6834
    status critical #d03b3b  serious #ec835a  warning #fab219  good #0ca30c
Diagram fills are deliberately light so the figures stay legible when the
report is printed in greyscale.

Run:  python scripts/build_figures.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Ellipse, FancyArrowPatch, FancyBboxPatch, Rectangle

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

DPI = 200

# palette
BLUE = "#2a78d6"
ORANGE = "#eb6834"
CRIT = "#d03b3b"
GOOD = "#0ca30c"
WARN = "#fab219"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"

# light fills for boxes (print-safe)
FILL_BLUE = "#dfeafb"
FILL_ORANGE = "#fbe4d9"
FILL_GREY = "#eeeeec"
FILL_GREEN = "#dff0df"
FILL_RED = "#fadedd"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "figure.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
})


def _save(fig, name):
    path = OUT / name
    fig.savefig(path, dpi=DPI, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    print("  wrote", path.name)
    return path


def box(ax, x, y, w, h, text, fill=FILL_BLUE, edge=BLUE, fontsize=9,
        bold=False, radius=0.02, text_color=INK):
    p = FancyBboxPatch((x, y), w, h,
                       boxstyle=f"round,pad=0.004,rounding_size={radius}",
                       linewidth=1.1, edgecolor=edge, facecolor=fill,
                       mutation_aspect=1)
    ax.add_patch(p)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fontsize, color=text_color,
            fontweight="bold" if bold else "normal", zorder=5,
            linespacing=1.45)
    return (x + w / 2, y + h / 2)


def arrow(ax, p1, p2, color=INK2, style="-|>", lw=1.2, rad=0.0, ls="-"):
    ax.add_patch(FancyArrowPatch(
        p1, p2, arrowstyle=style, mutation_scale=11, linewidth=lw,
        color=color, linestyle=ls,
        connectionstyle=f"arc3,rad={rad}", shrinkA=2, shrinkB=2, zorder=4))


def label(ax, x, y, text, fontsize=8, color=INK2, ha="center", style="normal",
          weight="normal"):
    ax.text(x, y, text, ha=ha, va="center", fontsize=fontsize, color=color,
            style=style, fontweight=weight, zorder=6)


def blank_ax(w, h):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    return fig, ax


# ----------------------------------------------------------------------
# Fig 1 - Gantt chart
# ----------------------------------------------------------------------

def fig_gantt():
    phases = [
        ("Problem formulation & literature survey", 0, 3),
        ("Architecture design & canonical model", 2, 3),
        ("Plan parser & deterministic rule engine", 4, 4),
        ("Knowledge base, reasoning & policy layer", 7, 4),
        ("CI/CD integration & Terraform modules", 10, 3),
        ("Azure provisioning & OIDC federation", 12, 2),
        ("Evaluation harness & benchmarking", 13, 3),
        ("Dashboard, documentation & reporting", 15, 3),
    ]
    fig, ax = plt.subplots(figsize=(9.4, 3.9))
    names = [p[0] for p in phases][::-1]
    for i, (name, start, dur) in enumerate(phases[::-1]):
        ax.barh(i, dur, left=start, height=0.55, color=BLUE,
                edgecolor="none", zorder=3)
        ax.text(start + dur + 0.18, i, f"{dur}w", va="center", ha="left",
                fontsize=8, color=INK2, zorder=4)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=9, color=INK)
    ax.set_xlabel("Project week", fontsize=9, color=INK2)
    ax.set_xlim(0, 19.5)
    ax.set_xticks(range(0, 19, 2))
    ax.tick_params(axis="x", colors=MUTED, labelsize=8)
    ax.tick_params(axis="y", length=0)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color("#c3c2b7")
    return _save(fig, "fig1_gantt.png")


# ----------------------------------------------------------------------
# Fig 2 - System architecture
# ----------------------------------------------------------------------

def fig_architecture():
    fig, ax = blank_ax(9.6, 6.4)

    # top row: pipeline up to plan.json
    a = box(ax, 2, 84, 19, 11, "Developer\ncommits .tf", FILL_GREY, MUTED, 9, True)
    b = box(ax, 27, 84, 19, 11, "GitHub Actions\nCI/CD triggered", FILL_GREY, MUTED, 9, True)
    c = box(ax, 52, 84, 19, 11, "terraform plan\n-out=tf.plan", FILL_GREY, MUTED, 9, True)
    d = box(ax, 77, 84, 20, 11, "plan.json\n(resource_changes)", FILL_GREY, MUTED, 9, True)
    arrow(ax, (21, 89.5), (27, 89.5))
    arrow(ax, (46, 89.5), (52, 89.5))
    arrow(ax, (71, 89.5), (77, 89.5))

    # gate container
    gate = FancyBboxPatch((6, 27), 88, 50,
                          boxstyle="round,pad=0.004,rounding_size=0.02",
                          linewidth=1.6, edgecolor=BLUE,
                          facecolor="#f5f9fe", zorder=1)
    ax.add_patch(gate)
    label(ax, 50, 73.5, "AGENT SECOPS  -  CAF / WAF COMPLIANCE GATE",
          fontsize=10.5, color=BLUE, weight="bold")
    arrow(ax, (87, 84), (87, 77.5), color=BLUE, lw=1.4)

    box(ax, 10, 60, 80, 9.5,
        "Layer 0  -  Normalisation:  provider types -> canonical Kind\n"
        "azurerm_storage_account | aws_s3_bucket | google_storage_bucket  ->  OBJECT_STORAGE",
        FILL_GREY, MUTED, 8.4)

    box(ax, 10, 48.5, 38, 9,
        "Layer 1  -  Deterministic rules\n22 CAF/WAF checks, confidence 1.0",
        FILL_BLUE, BLUE, 8.6, True)
    box(ax, 52, 48.5, 38, 9,
        "Layer 2  -  Framework reasoning\nintent no rule encodes",
        FILL_ORANGE, ORANGE, 8.6, True)

    box(ax, 10, 37, 38, 8.5,
        "22 rules  |  9 pillar areas\nCAF: Gov, LZ, Cost, Identity",
        "#eef4fd", "#9ec5f4", 8)
    box(ax, 52, 37, 38, 8.5,
        "Knowledge base (YAML)\nretrieval keyed on resource kind",
        "#fdf0e9", "#f3b394", 8)

    arrow(ax, (29, 60), (29, 57.5), color=BLUE)
    arrow(ax, (71, 60), (71, 57.5), color=ORANGE)
    arrow(ax, (29, 48.5), (29, 45.5), color=BLUE, style="<|-|>", lw=1.0)
    arrow(ax, (71, 48.5), (71, 45.5), color=ORANGE, style="<|-|>", lw=1.0)

    box(ax, 10, 29.5, 80, 6.5,
        "Layer 3  -  Organisational policy:  severity thresholds  |  rule overrides  |  time-boxed waivers",
        FILL_GREY, MUTED, 8.4)
    arrow(ax, (29, 37), (29, 36.1), color=MUTED)
    arrow(ax, (71, 37), (71, 36.1), color=MUTED)

    # verdict split
    arrow(ax, (50, 29.5), (50, 24), color=BLUE, lw=1.5)
    label(ax, 50, 22, "VERDICT", fontsize=9, color=INK, weight="bold")

    box(ax, 6, 9, 38, 11,
        "BLOCK   (exit 2)\nPipeline halted - report posted to PR\nNothing is ever provisioned",
        FILL_RED, CRIT, 8.6, True)
    box(ax, 56, 9, 38, 11,
        "PASS   (exit 0)\nterraform apply proceeds\n-> Azure  |  AWS  |  GCP",
        FILL_GREEN, GOOD, 8.6, True)
    # straight verdict branches, terminating on the box edge
    arrow(ax, (45, 21), (25, 20.2), color=CRIT, lw=1.4)
    arrow(ax, (55, 21), (75, 20.2), color=GOOD, lw=1.4)

    arrow(ax, (25, 9), (25, 5.2), color=CRIT, lw=1.0)
    label(ax, 25, 3.6, "compliance report returned to the developer",
          fontsize=7.5, color=CRIT, style="italic")

    return _save(fig, "fig2_architecture.png")


# ----------------------------------------------------------------------
# Fig 3 - real gate output rendered as a terminal capture
# ----------------------------------------------------------------------

def fig_gate_output():
    src = OUT / "_gate_block.txt"
    if src.exists():
        lines = src.read_text(encoding="utf-8", errors="replace").splitlines()
    else:
        lines = ["(gate output not captured)"]
    lines = [l.rstrip() for l in lines][:22]

    fig, ax = plt.subplots(figsize=(9.6, 0.30 * len(lines) + 0.9))
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    fig.patch.set_facecolor("#1a1a19")
    ax.add_patch(Rectangle((0, 0), 1, 1, transform=ax.transAxes,
                           facecolor="#1a1a19", zorder=0))

    ax.text(0.012, 0.975, "$ python -m agent.cli evaluate --plan "
                          "examples/plans/azure_noncompliant.plan.json",
            fontsize=7.6, family="DejaVu Sans Mono", color="#8fd18f",
            va="top", transform=ax.transAxes)

    y = 0.90
    step = 0.86 / max(len(lines), 1)
    for ln in lines:
        col = "#c3c2b7"
        if ln.startswith("Agent SecOps:"):
            col = "#ff8f8f"
        elif "CRITICAL" in ln:
            col = "#ef7b7b"
        elif "HIGH" in ln:
            col = "#f0a878"
        elif "MEDIUM" in ln:
            col = "#e8c96a"
        elif ln.strip().startswith("exit="):
            col = "#8fd18f"
        ax.text(0.012, y, ln[:118], fontsize=7.0, family="DejaVu Sans Mono",
                color=col, va="top", transform=ax.transAxes)
        y -= step
    return _save(fig, "fig3_gate_output.png")


# ----------------------------------------------------------------------
# Fig 4 - Data flow diagram
# ----------------------------------------------------------------------

def fig_dfd():
    fig, ax = blank_ax(9.6, 5.8)

    # external entities
    box(ax, 1, 74, 17, 10, "Developer\n(external entity)", FILL_GREY, INK2, 8.5, True)
    box(ax, 1, 12, 17, 10, "CI/CD Pipeline\n(external entity)", FILL_GREY, INK2, 8.5, True)

    def proc(x, y, num, name):
        c = Circle((x, y), 8.6, facecolor=FILL_BLUE, edgecolor=BLUE, lw=1.2, zorder=3)
        ax.add_patch(c)
        ax.text(x, y + 2.4, num, ha="center", va="center", fontsize=8,
                color=BLUE, fontweight="bold", zorder=5)
        ax.text(x, y - 2.2, name, ha="center", va="center", fontsize=7.4,
                color=INK, zorder=5, linespacing=1.3)
        return (x, y)

    p1 = proc(32, 79, "1.0", "Parse &\nnormalise")
    p2 = proc(58, 79, "2.0", "Apply\nrules")
    p3 = proc(84, 79, "3.0", "Reason over\nguidance")
    p4 = proc(58, 40, "4.0", "Aggregate\nverdict")
    p5 = proc(24, 40, "5.0", "Render\nreports")

    # data stores (open rectangles)
    def store(x, y, w, tag, name):
        ax.add_patch(Rectangle((x, y), w, 7.5, facecolor="#faf7ee",
                               edgecolor=MUTED, lw=1.1, zorder=3))
        ax.plot([x, x + w], [y + 7.5, y + 7.5], color=MUTED, lw=1.1, zorder=4)
        ax.plot([x, x + w], [y, y], color=MUTED, lw=1.1, zorder=4)
        ax.text(x + 3, y + 3.7, tag, ha="left", va="center", fontsize=7.6,
                color=INK2, fontweight="bold", zorder=5)
        ax.text(x + w / 2 + 3, y + 3.7, name, ha="center", va="center",
                fontsize=7.4, color=INK, zorder=5)
        return (x + w / 2, y + 3.7)

    d1 = store(72, 58, 26, "D1", "CAF/WAF knowledge base")
    d2 = store(72, 25, 26, "D2", "policy.yaml")

    # flows
    arrow(ax, (18, 79), (23.4, 79)); label(ax, 20.5, 82.4, "plan.json", 7)
    arrow(ax, (40.6, 79), (49.4, 79)); label(ax, 45, 82.4, "normalised\nresources", 7)
    arrow(ax, (66.6, 79), (75.4, 79)); label(ax, 71, 82.6, "resources +\nrule findings", 7)
    arrow(ax, (84, 70.4), (84, 65.5), style="<|-", color=MUTED)
    label(ax, 92, 68, "pillar guidance", 7)
    arrow(ax, (84, 70.4), (63, 47.5), color=ORANGE, rad=0.12)
    label(ax, 79, 55, "reasoned\nfindings", 7, color=ORANGE)
    arrow(ax, (58, 70.4), (58, 48.6)); label(ax, 63.5, 60, "rule findings", 7)
    arrow(ax, (72, 28.7), (66, 36), style="<|-", color=MUTED)
    label(ax, 76, 34.5, "thresholds,\nwaivers", 7)
    arrow(ax, (49.4, 40), (32.6, 40)); label(ax, 41, 43.4, "verdict +\nfindings", 7)
    arrow(ax, (24, 31.4), (13, 22.5)); label(ax, 13, 29, "Markdown / JSON /\nSARIF + exit code", 7)
    arrow(ax, (9.5, 74), (9.5, 22.5), style="-|>", color=MUTED, ls=(0, (4, 3)))
    label(ax, 3.6, 48, "commits", 7, ha="center")

    label(ax, 50, 4, "External entity           Process           Data store",
          7.5, color=MUTED)
    return _save(fig, "fig4_dfd.png")


# ----------------------------------------------------------------------
# Fig 5 - Use case diagram
# ----------------------------------------------------------------------

def fig_usecase():
    fig, ax = blank_ax(9.6, 6.2)

    def actor(x, y, name):
        ax.add_patch(Circle((x, y + 7.5), 2.6, fill=False, ec=INK, lw=1.2))
        ax.plot([x, x], [y + 5, y - 1], color=INK, lw=1.2)
        ax.plot([x - 3.6, x + 3.6], [y + 3.2, y + 3.2], color=INK, lw=1.2)
        ax.plot([x, x - 3.2], [y - 1, y - 6], color=INK, lw=1.2)
        ax.plot([x, x + 3.2], [y - 1, y - 6], color=INK, lw=1.2)
        ax.text(x, y - 9.5, name, ha="center", va="center", fontsize=8,
                color=INK, fontweight="bold", linespacing=1.3)
        return (x, y + 2)

    # system boundary
    ax.add_patch(Rectangle((27, 8), 46, 84, fill=False, ec=INK2, lw=1.3))
    label(ax, 50, 88, "Agent SecOps", 9.5, color=INK, weight="bold")

    def uc(x, y, text):
        ax.add_patch(Ellipse((x, y), 38, 9.2, facecolor=FILL_BLUE,
                             edgecolor=BLUE, lw=1.1, zorder=3))
        ax.text(x, y, text, ha="center", va="center", fontsize=7.6,
                color=INK, zorder=5, linespacing=1.3)
        return (x, y)

    u1 = uc(50, 79, "Evaluate Terraform plan")
    u2 = uc(50, 68, "Produce compliance verdict")
    u3 = uc(50, 57, "Reason over CAF/WAF guidance")
    u4 = uc(50, 46, "Publish compliance report")
    u5 = uc(50, 35, "Gate the deployment")
    u6 = uc(50, 24, "Configure policy & waivers")
    u7 = uc(50, 13.5, "Review benchmark results")

    dev = actor(9, 68, "Developer")
    pipe = actor(9, 32, "CI/CD\nPipeline")
    plat = actor(91, 62, "Platform\nEngineer")
    svc = actor(91, 26, "Reasoning\nService")

    for a, u in ((dev, u1), (dev, u4), (dev, u7)):
        arrow(ax, a, (u[0] - 19, u[1]), color=INK2, style="-", lw=1.0)
    for a, u in ((pipe, u1), (pipe, u5)):
        arrow(ax, a, (u[0] - 19, u[1]), color=INK2, style="-", lw=1.0)
    for a, u in ((plat, u6), (plat, u7)):
        arrow(ax, a, (u[0] + 19, u[1]), color=INK2, style="-", lw=1.0)
    arrow(ax, svc, (u3[0] + 19, u3[1]), color=INK2, style="-", lw=1.0)

    arrow(ax, (50, 74.4), (50, 72.6), style="-|>", color=MUTED, ls=(0, (3, 2)))
    label(ax, 61.5, 73.5, "<<include>>", 6.6, color=MUTED, style="italic")
    arrow(ax, (50, 63.4), (50, 61.6), style="-|>", color=MUTED, ls=(0, (3, 2)))
    label(ax, 61.5, 62.5, "<<include>>", 6.6, color=MUTED, style="italic")
    arrow(ax, (50, 41.4), (50, 39.6), style="-|>", color=MUTED, ls=(0, (3, 2)))
    label(ax, 61.5, 40.5, "<<include>>", 6.6, color=MUTED, style="italic")
    return _save(fig, "fig5_usecase.png")


# ----------------------------------------------------------------------
# Fig 6 - Class diagram
# ----------------------------------------------------------------------

def fig_class():
    fig, ax = blank_ax(9.6, 7.0)

    def cls(x, y, w, name, attrs, meths, fill=FILL_BLUE, edge=BLUE, italic=False):
        line_h = 3.3
        h_name = 5.6
        h_a = line_h * len(attrs) + 1.6
        h_m = line_h * len(meths) + 1.6
        h = h_name + h_a + h_m
        ax.add_patch(Rectangle((x, y - h), w, h, facecolor=fill,
                               edgecolor=edge, lw=1.15, zorder=3))
        ax.plot([x, x + w], [y - h_name, y - h_name], color=edge, lw=1.0, zorder=4)
        ax.plot([x, x + w], [y - h_name - h_a, y - h_name - h_a],
                color=edge, lw=1.0, zorder=4)
        ax.text(x + w / 2, y - h_name / 2, name, ha="center", va="center",
                fontsize=8.0, fontweight="bold", color=INK, zorder=5,
                style="italic" if italic else "normal")
        yy = y - h_name - 2.9
        for a in attrs:
            ax.text(x + 1.8, yy, a, ha="left", va="center", fontsize=6.6,
                    color=INK2, zorder=5)
            yy -= line_h
        yy = y - h_name - h_a - 2.9
        for m in meths:
            ax.text(x + 1.8, yy, m, ha="left", va="center", fontsize=6.6,
                    color=INK2, zorder=5)
            yy -= line_h
        return {"cx": x + w / 2, "top": y, "bot": y - h, "l": x, "r": x + w,
                "cy": y - h / 2}

    # --- row 1: data model -------------------------------------------
    res = cls(1, 99, 29, "Resource",
              ["+ address: str", "+ provider: Provider", "+ kind: Kind",
               "+ action: Action"],
              ["+ get(path)", "+ is_mutating"])

    find = cls(35.5, 99, 30, "Finding",
               ["+ rule_id: str", "+ pillar: Pillar", "+ severity: Severity",
                "+ source / confidence"],
               ["+ to_dict()"])

    gate = cls(71, 99, 28, "GateResult",
               ["+ verdict: Verdict", "+ findings: List[Finding]",
                "+ duration_ms: int"],
               ["+ active", "+ to_dict()"])

    # --- row 2: behaviour --------------------------------------------
    rule = cls(1, 62, 29, "Rule  «abstract»",
               ["+ id: str", "+ pillar: Pillar", "+ severity: Severity",
                "+ rationale: str"],
               ["+ check(r)", "+ evaluate(r)"], italic=True)

    reasoner = cls(35.5, 62, 30, "Reasoner  «abstract»",
                   ["+ name: str"],
                   ["+ analyse(resources,", "     already_found)"],
                   FILL_ORANGE, ORANGE, italic=True)

    policy = cls(71, 62, 28, "Policy",
                 ["+ block_at: Severity", "+ remediate_at: Severity",
                  "+ waivers: List[Waiver]"],
                 ["+ decide(findings)", "+ apply_waivers(f)"], FILL_GREY, INK2)

    # --- row 3: concrete implementations ------------------------------
    caf = cls(1, 26, 20.5, "CAFRule", [], ["+ check(r)"], "#eef4fd", "#9ec5f4")
    waf = cls(24.5, 26, 20.5, "WAFRule", [], ["+ check(r)"], "#eef4fd", "#9ec5f4")
    off = cls(52, 26, 22, "OfflineReasoner", [], ["+ analyse(...)"],
              "#fdf0e9", "#f3b394")
    llm = cls(77, 26, 22, "LLMReasoner", [], ["+ analyse(...)"],
              "#fdf0e9", "#f3b394")

    # --- associations -------------------------------------------------
    arrow(ax, (res["r"], 90), (find["l"], 90), style="-", color=INK2)
    label(ax, (res["r"] + find["l"]) / 2, 92.5, "produces", 6.6)
    arrow(ax, (find["r"], 90), (gate["l"], 90), style="-", color=INK2)
    label(ax, (find["r"] + gate["l"]) / 2, 92.5, "aggregated in", 6.6)

    arrow(ax, (rule["cx"], rule["top"]), (rule["cx"], res["bot"]),
          style="-|>", color=INK2)
    label(ax, rule["cx"] + 9, (rule["top"] + res["bot"]) / 2, "evaluates", 6.6)
    arrow(ax, (reasoner["cx"], reasoner["top"]), (reasoner["cx"], find["bot"]),
          style="-|>", color=ORANGE)
    label(ax, reasoner["cx"] + 9, (reasoner["top"] + find["bot"]) / 2,
          "emits", 6.6, color=ORANGE)
    arrow(ax, (policy["cx"], policy["top"]), (policy["cx"], gate["bot"]),
          style="-|>", color=INK2)
    label(ax, policy["cx"] + 8, (policy["top"] + gate["bot"]) / 2,
          "decides", 6.6)

    # --- generalisation (subclass -> parent) ---------------------------
    for child, parent, col in ((caf, rule, INK2), (waf, rule, INK2),
                               (off, reasoner, ORANGE), (llm, reasoner, ORANGE)):
        # Route below the lowest parent edge so the arrowhead has room.
        joint = 30.0
        ax.plot([child["cx"], child["cx"]], [child["top"], joint],
                color=col, lw=1.1, zorder=3)
        ax.plot([child["cx"], parent["cx"]], [joint, joint], color=col,
                lw=1.1, zorder=3)
        arrow(ax, (parent["cx"], joint), (parent["cx"], parent["bot"]),
              style="-|>", color=col, lw=1.1)

    label(ax, 50, 6,
          "Rules and reasoners are open extension points: a new check registers "
          "itself without modifying the engine.", 7.2, color=MUTED,
          style="italic")
    return _save(fig, "fig6_class.png")


# ----------------------------------------------------------------------
# Fig 7 - Sequence diagram
# ----------------------------------------------------------------------

def fig_sequence():
    fig, ax = blank_ax(9.8, 6.4)

    actors = [
        ("GitHub\nActions", 8),
        ("agent.cli", 25),
        ("engine", 42),
        ("plan_parser", 58),
        ("Rule\nregistry", 74),
        ("Reasoner", 90),
    ]
    top = 92
    bottom = 12
    for name, x in actors:
        box(ax, x - 7, top, 14, 6.5, name, FILL_GREY, INK2, 7.6, True)
        ax.plot([x, x], [top, bottom], color=MUTED, lw=0.9,
                linestyle=(0, (4, 3)), zorder=1)

    X = {n.replace("\n", " "): x for n, x in actors}
    gh, cli, eng, par, reg, rsn = (X["GitHub Actions"], X["agent.cli"],
                                   X["engine"], X["plan_parser"],
                                   X["Rule registry"], X["Reasoner"])

    def act(x, y0, y1):
        ax.add_patch(Rectangle((x - 1.5, y1), 3.0, y0 - y1,
                               facecolor="#e6eefb", edgecolor=BLUE,
                               lw=0.8, zorder=2))

    def msg(x1, x2, y, text, ret=False):
        arrow(ax, (x1, y), (x2, y), color=INK2 if not ret else MUTED,
              style="-|>", lw=1.0, ls="-" if not ret else (0, (4, 2)))
        ax.text((x1 + x2) / 2, y + 1.9, text, ha="center", va="bottom",
                fontsize=6.8, color=INK2 if not ret else MUTED, zorder=6)

    act(cli, 85, 20); act(eng, 80, 26); act(par, 76, 70)
    act(reg, 64, 54); act(rsn, 50, 40)

    msg(gh, cli, 85, "evaluate --plan plan.json")
    msg(cli, eng, 80, "evaluate_plan(plan, policy)")
    msg(eng, par, 76, "load_plan()")
    msg(par, eng, 70, "PlanSummary (canonical resources)", ret=True)
    msg(eng, reg, 64, "rule.evaluate(resource)  [x22]")
    msg(reg, eng, 54, "rule findings (confidence 1.0)", ret=True)
    msg(eng, rsn, 50, "analyse(resources, already_found)")
    msg(rsn, eng, 40, "reasoned findings (advisory)", ret=True)

    ax.add_patch(Rectangle((eng - 12, 30), 26, 6.5, facecolor="#f5f9fe",
                           edgecolor=BLUE, lw=0.9, zorder=3))
    ax.text(eng + 1, 33.2, "apply waivers + thresholds", ha="center",
            va="center", fontsize=6.8, color=INK, zorder=5)

    msg(eng, cli, 26, "GateResult (verdict)", ret=True)
    msg(cli, gh, 20, "reports + exit code 0 / 1 / 2", ret=True)

    ax.add_patch(Rectangle((3, 3), 94, 7, fill=False, ec=MUTED, lw=0.9,
                           linestyle=(0, (4, 3))))
    ax.text(50, 6.5,
            "exit 2  ->  workflow fails, report posted to the pull request, "
            "terraform apply is never reached", ha="center", va="center",
            fontsize=7.2, color=CRIT, zorder=5)
    return _save(fig, "fig7_sequence.png")


# ----------------------------------------------------------------------
# Fig 8 - Benchmark results (used in the deck and the report)
# ----------------------------------------------------------------------

def fig_benchmark():
    data_path = ROOT / "docs" / "benchmark-results.json"
    if data_path.exists():
        d = json.loads(data_path.read_text(encoding="utf-8"))
        suites = d["suites"]
        totals = d["totals"]
    else:
        return None

    labels = [s["plan"].replace("_noncompliant.plan.json", "").upper()
              for s in suites]
    rules = [s["detected_rules_only"] for s in suites]
    both = [s["detected_with_reasoning"] for s in suites]
    seeded = [s["seeded"] for s in suites]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.6, 3.5),
                                   gridspec_kw={"width_ratios": [1.35, 1]})

    y = range(len(labels))
    h = 0.34
    ax1.barh([i + h / 2 + 0.02 for i in y], rules, height=h, color=BLUE,
             label="Deterministic rules only", zorder=3)
    ax1.barh([i - h / 2 - 0.02 for i in y], both, height=h, color=ORANGE,
             label="Rules + reasoning layer", zorder=3)
    for i, (r, b, s) in enumerate(zip(rules, both, seeded)):
        ax1.text(r + 0.4, i + h / 2 + 0.02, str(r), va="center", fontsize=8,
                 color=INK)
        ax1.text(b + 0.4, i - h / 2 - 0.02, str(b), va="center", fontsize=8,
                 color=INK)
        ax1.text(max(r, b) + 2.6, i, f"of {s}", va="center",
                 fontsize=7.5, color=MUTED)
    ax1.set_yticks(list(y))
    ax1.set_yticklabels(labels, fontsize=9, color=INK)
    ax1.set_xlabel("Seeded violations detected", fontsize=8.5, color=INK2)
    ax1.set_xlim(0, max(seeded) + 5)
    ax1.xaxis.grid(True, color=GRID, lw=0.8, zorder=0)
    ax1.set_axisbelow(True)
    ax1.tick_params(axis="x", colors=MUTED, labelsize=8)
    ax1.tick_params(axis="y", length=0)
    for s in ("top", "right", "left"):
        ax1.spines[s].set_visible(False)
    ax1.spines["bottom"].set_color("#c3c2b7")
    ax1.legend(fontsize=7.6, frameon=False, loc="upper right",
               bbox_to_anchor=(1.0, 1.02))
    ax1.set_title("Detection per cloud provider", fontsize=9.5, color=INK,
                  loc="left", pad=10)

    ax2.axis("off")
    ax2.set_xlim(0, 1); ax2.set_ylim(0, 1)
    stats = [
        (f"{totals['seeded_violations']}", "seeded violations", INK),
        (f"{totals['recall_rules_only']*100:.1f}%", "rules alone", BLUE),
        (f"{totals['recall_with_reasoning']*100:.0f}%", "with reasoning", ORANGE),
        (f"+{totals['reasoning_uplift']}", "recovered by reasoning only", ORANGE),
        (f"{totals['false_positives_on_clean_plan']}", "false positives", GOOD),
    ]
    yy = 0.92
    for val, cap, col in stats:
        ax2.text(0.02, yy, val, fontsize=17, color=col, fontweight="bold",
                 va="top")
        ax2.text(0.34, yy - 0.035, cap, fontsize=8.6, color=INK2, va="top")
        yy -= 0.19
    ax2.set_title("Headline results", fontsize=9.5, color=INK, loc="left",
                  pad=10)

    return _save(fig, "fig8_benchmark.png")


# ----------------------------------------------------------------------

def main():
    print("Generating figures ->", OUT)
    fig_gantt()
    fig_architecture()
    fig_gate_output()
    fig_dfd()
    fig_usecase()
    fig_class()
    fig_sequence()
    fig_benchmark()
    print("Done.")


if __name__ == "__main__":
    main()
