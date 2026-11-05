"""Tiny eval for the Layer 4 advisor against a live Ollama model.

Usage: python scripts/eval_advisor.py [model]
Reports, per seeded plan: findings advised vs rejected by guardrails, whether
the verdict stayed identical, and the average seconds per advised finding.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.advisor import Advisor  # noqa: E402
from agent.config import load_policy  # noqa: E402
from agent.engine import evaluate_plan  # noqa: E402
from agent.plan_parser import load_plan  # noqa: E402

PLANS = ["azure_noncompliant", "aws_noncompliant", "gcp_noncompliant"]


def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 else "qwen2.5:3b"
    policy = load_policy(str(ROOT / "policies" / "policy.yaml"))
    total_ok = total_n = 0
    print("| plan | considered | advised | rejected | verdict same | s/finding |")
    print("|---|---|---|---|---|---|")
    for name in PLANS:
        path = str(ROOT / "examples" / "plans" / (name + ".plan.json"))
        base = evaluate_plan(load_plan(path), policy)
        t = time.time()
        res = evaluate_plan(load_plan(path), policy, advisor=Advisor(model=model, max_findings=5))
        s = res.stats["advisor"]
        per = (time.time() - t) / max(1, s["considered"])
        total_ok += s["advised"]
        total_n += s["considered"]
        print("| {} | {} | {} | {} | {} | {:.1f} |".format(
            name, s["considered"], s["advised"], s["rejected_by_guardrails"],
            res.verdict is base.verdict, per))
    print("\nValid, grounded advice: {}/{} ({}) with {}".format(
        total_ok, total_n, "{:.0%}".format(total_ok / max(1, total_n)), model))


if __name__ == "__main__":
    main()
