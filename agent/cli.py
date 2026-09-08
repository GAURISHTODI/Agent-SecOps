"""Command-line entry point -- this is what GitHub Actions runs.

    python -m agent.cli evaluate --plan plan.json --markdown report.md

Exit codes are the gate:
    0  pass       -> the workflow continues to terraform apply
    1  remediate  -> continues only if --soft-fail is set
    2  block      -> the workflow stops
    3  usage/parse error
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

from .config import load_policy
from .engine import evaluate_plan
from .models import Verdict
from .plan_parser import PlanParseError, load_plan
from .report import render_console, render_json, render_markdown, render_sarif
from .rules.base import all_rules

EXIT_PASS = 0
EXIT_REMEDIATE = 1
EXIT_BLOCK = 2
EXIT_ERROR = 3


def _write(path: Optional[str], content: str) -> None:
    if not path:
        return
    target = Path(path)
    if target.parent and str(target.parent) not in ("", "."):
        target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _emit_github_outputs(result, markdown: str) -> None:
    """Publish verdict + report to the GitHub Actions job context.

    Written defensively: outside Actions these env vars are absent and the
    function is a no-op, so local runs behave identically.
    """
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as handle:
            handle.write("verdict={}\n".format(result.verdict.value))
            handle.write("findings={}\n".format(len(result.active)))
            handle.write(
                "blocking={}\n".format(
                    "true" if result.verdict == Verdict.BLOCK else "false"
                )
            )
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(markdown + "\n")


def cmd_evaluate(args: argparse.Namespace) -> int:
    try:
        plan = load_plan(args.plan)
    except PlanParseError as exc:
        print("Agent SecOps: {}".format(exc), file=sys.stderr)
        return EXIT_ERROR

    policy = load_policy(args.policy)
    if args.reasoner:
        policy.reasoner.provider = args.reasoner
    if args.no_reasoner:
        policy.reasoner.enabled = False

    result = evaluate_plan(plan, policy)

    markdown = render_markdown(result)
    _write(args.markdown, markdown)
    _write(args.json, render_json(result))
    _write(args.sarif, render_sarif(result))
    _emit_github_outputs(result, markdown)

    print(markdown if args.format == "markdown" else render_console(result))

    if result.verdict == Verdict.BLOCK:
        return EXIT_PASS if args.soft_fail else EXIT_BLOCK
    if result.verdict == Verdict.REMEDIATE:
        return EXIT_PASS if args.soft_fail else EXIT_REMEDIATE
    return EXIT_PASS


def cmd_rules(args: argparse.Namespace) -> int:
    rules = sorted(all_rules(), key=lambda r: r.id)
    if args.format == "markdown":
        print("| Rule | Pillar | Severity | Title |")
        print("|---|---|---|---|")
        for r in rules:
            print(
                "| `{}` | `{}` | {} | {} |".format(
                    r.id, r.pillar.value, r.severity.value, r.title
                )
            )
    else:
        for r in rules:
            print(
                "{:<14} {:<28} {:<9} {}".format(
                    r.id, r.pillar.value, r.severity.value, r.title
                )
            )
        print("\n{} rules across {} pillars.".format(
            len(rules), len({r.pillar for r in rules})
        ))
    return EXIT_PASS


def cmd_explain(args: argparse.Namespace) -> int:
    """Print the framework rationale behind one rule -- used in the viva demo."""
    for rule in all_rules():
        if rule.id.lower() == args.rule_id.lower():
            print("{}: {}".format(rule.id, rule.title))
            print("Pillar     : {}".format(rule.pillar.value))
            print("Severity   : {}".format(rule.severity.value))
            print("Applies to : {}".format(
                ", ".join(k.value for k in rule.kinds) or "all resource kinds"
            ))
            print("\nWhy the framework requires this:\n  {}".format(rule.rationale))
            print("\nRemediation:\n  {}".format(rule.remediation))
            if rule.terraform_fix:
                print("\nTerraform:\n{}".format(rule.terraform_fix))
            return EXIT_PASS
    print("Unknown rule id: {}".format(args.rule_id), file=sys.stderr)
    return EXIT_ERROR


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-secops",
        description="CAF/WAF compliance gate for Terraform plans in CI/CD.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    ev = sub.add_parser("evaluate", help="Evaluate a Terraform plan JSON file.")
    ev.add_argument("--plan", required=True, help="Path to terraform show -json output.")
    ev.add_argument("--policy", help="Path to policy.yaml (defaults to policies/policy.yaml).")
    ev.add_argument("--markdown", help="Write the PR report here.")
    ev.add_argument("--json", dest="json", help="Write machine-readable results here.")
    ev.add_argument("--sarif", help="Write SARIF for GitHub code scanning here.")
    ev.add_argument(
        "--reasoner",
        choices=["offline", "azure_openai", "anthropic", "none"],
        help="Override the reasoning layer from policy.",
    )
    ev.add_argument(
        "--no-reasoner", action="store_true", help="Run deterministic rules only."
    )
    ev.add_argument(
        "--soft-fail",
        action="store_true",
        help="Always exit 0 (report-only mode, for onboarding an existing repo).",
    )
    ev.add_argument(
        "--format", choices=["console", "markdown"], default="console"
    )
    ev.set_defaults(func=cmd_evaluate)

    rl = sub.add_parser("rules", help="List the rule catalogue.")
    rl.add_argument("--format", choices=["console", "markdown"], default="console")
    rl.set_defaults(func=cmd_rules)

    ex = sub.add_parser("explain", help="Explain one rule and its framework basis.")
    ex.add_argument("rule_id")
    ex.set_defaults(func=cmd_explain)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
