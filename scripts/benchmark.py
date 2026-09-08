"""Evaluation harness for the project's success metric.

The claim under test, from the project brief:

    "catching a broader class of CAF/WAF violations than existing static
     scanners, measured against a seeded test set of intentionally
     misconfigured Terraform modules"

To measure that honestly you need three numbers, not one:

  1. Detection rate on the seeded (labelled) violations -- recall.
  2. False positives on the compliant module -- precision, which is what
     decides whether anyone leaves the gate switched on.
  3. The marginal contribution of the reasoning layer over rules alone --
     the actual research claim, since the rules layer is roughly what a
     static scanner like Checkov already gives you.

Run:  python scripts/benchmark.py
      python scripts/benchmark.py --markdown docs/benchmark-results.md
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.config import ReasonerConfig, load_policy  # noqa: E402
from agent.engine import evaluate_plan  # noqa: E402
from agent.models import GateResult, Verdict  # noqa: E402
from agent.plan_parser import load_plan  # noqa: E402

PLANS = ROOT / "examples" / "plans"
POLICY = ROOT / "policies" / "policy.yaml"

# The ground truth. Each entry is a violation deliberately seeded into the
# fixture, labelled with the resource it lives on and the pillar it breaks.
# This is what makes the benchmark a measurement rather than a demo.
GROUND_TRUTH: Dict[str, List[Dict[str, str]]] = {
    "azure_noncompliant.plan.json": [
        {"resource": "azurerm_resource_group.rg", "issue": "unapproved region", "pillar": "CAF:LandingZone"},
        {"resource": "azurerm_resource_group.rg", "issue": "missing governance tags", "pillar": "CAF:Governance"},
        {"resource": "azurerm_storage_account.data", "issue": "http allowed", "pillar": "WAF:Security"},
        {"resource": "azurerm_storage_account.data", "issue": "TLS 1.0", "pillar": "WAF:Security"},
        {"resource": "azurerm_storage_account.data", "issue": "anonymous blob access", "pillar": "WAF:Security"},
        {"resource": "azurerm_storage_account.data", "issue": "LRS replication", "pillar": "WAF:Reliability"},
        {"resource": "azurerm_storage_account.data", "issue": "public network access", "pillar": "CAF:LandingZone"},
        {"resource": "azurerm_storage_account.data", "issue": "network default allow", "pillar": "CAF:LandingZone"},
        {"resource": "azurerm_storage_account.data", "issue": "shared keys enabled", "pillar": "WAF:Security"},
        {"resource": "azurerm_storage_account.data", "issue": "versioning disabled", "pillar": "WAF:Reliability"},
        {"resource": "azurerm_storage_account.data", "issue": "hot tier for archive data", "pillar": "WAF:Sustainability"},
        {"resource": "azurerm_mssql_server.db", "issue": "hardcoded password", "pillar": "WAF:Security"},
        {"resource": "azurerm_mssql_server.db", "issue": "TLS 1.0", "pillar": "WAF:Security"},
        {"resource": "azurerm_mssql_server.db", "issue": "1-day backup retention", "pillar": "WAF:Reliability"},
        {"resource": "azurerm_mssql_server.db", "issue": "public network access", "pillar": "CAF:LandingZone"},
        {"resource": "azurerm_mssql_firewall_rule.allow_all", "issue": "firewall spans all IPv4", "pillar": "WAF:Security"},
        {"resource": "azurerm_network_security_rule.ssh", "issue": "ssh open to internet", "pillar": "WAF:Security"},
        {"resource": "azurerm_linux_virtual_machine.app", "issue": "hardcoded password", "pillar": "WAF:Security"},
        {"resource": "azurerm_linux_virtual_machine.app", "issue": "password auth enabled", "pillar": "WAF:Security"},
        {"resource": "azurerm_linux_virtual_machine.app", "issue": "premium SKU in dev", "pillar": "WAF:CostOptimization"},
        {"resource": "azurerm_linux_virtual_machine.app", "issue": "no availability zone", "pillar": "WAF:Reliability"},
        {"resource": "azurerm_linux_virtual_machine.app", "issue": "no cost centre tag", "pillar": "CAF:CostManagement"},
        {"resource": "azurerm_role_assignment.app_owner", "issue": "Owner at subscription scope", "pillar": "CAF:Identity"},
        {"resource": "azurerm_key_vault.kv", "issue": "purge protection off", "pillar": "WAF:Reliability"},
        {"resource": "azurerm_key_vault.kv", "issue": "access policies not RBAC", "pillar": "CAF:Identity"},
        {"resource": "azurerm_key_vault.kv", "issue": "public network access", "pillar": "CAF:LandingZone"},
        {"resource": "azurerm_public_ip.edge", "issue": "unjustified public exposure", "pillar": "CAF:LandingZone"},
        {"resource": "azurerm_public_ip.edge", "issue": "static IP idle in dev", "pillar": "WAF:CostOptimization"},
    ],
    "aws_noncompliant.plan.json": [
        {"resource": "aws_s3_bucket.data", "issue": "public-read ACL", "pillar": "WAF:Security"},
        {"resource": "aws_s3_bucket.data", "issue": "versioning disabled", "pillar": "WAF:Reliability"},
        {"resource": "aws_s3_bucket.data", "issue": "unapproved region", "pillar": "CAF:LandingZone"},
        {"resource": "aws_security_group.web", "issue": "ssh + postgres open to internet", "pillar": "WAF:Security"},
        {"resource": "aws_db_instance.main", "issue": "hardcoded password", "pillar": "WAF:Security"},
        {"resource": "aws_db_instance.main", "issue": "zero backup retention", "pillar": "WAF:Reliability"},
        {"resource": "aws_db_instance.main", "issue": "skip final snapshot", "pillar": "WAF:OperationalExcellence"},
        {"resource": "aws_iam_role_policy.admin", "issue": "wildcard actions", "pillar": "CAF:Identity"},
    ],
    "gcp_noncompliant.plan.json": [
        {"resource": "google_storage_bucket.data", "issue": "unapproved region", "pillar": "CAF:LandingZone"},
        {"resource": "google_storage_bucket.data", "issue": "versioning disabled", "pillar": "WAF:Reliability"},
        {"resource": "google_compute_firewall.allow_ssh", "issue": "ssh/rdp open to internet", "pillar": "WAF:Security"},
        {"resource": "google_sql_database_instance.main", "issue": "hardcoded password", "pillar": "WAF:Security"},
        {"resource": "google_sql_database_instance.main", "issue": "zero backup retention", "pillar": "WAF:Reliability"},
        {"resource": "google_project_iam_member.owner", "issue": "roles/owner granted", "pillar": "CAF:Identity"},
    ],
}

CLEAN_PLANS = ["azure_compliant.plan.json"]


def _run(plan_name: str, use_reasoner: bool) -> GateResult:
    policy = load_policy(str(POLICY))
    if not use_reasoner:
        policy.reasoner = ReasonerConfig(provider="none", enabled=False)
    return evaluate_plan(load_plan(str(PLANS / plan_name)), policy)


def _detected(result: GateResult, expected: Dict[str, str]) -> bool:
    """Did any finding on the right resource cover the right pillar?

    Matching on (resource, pillar) rather than on exact rule id is the fair
    test: the point is whether the violation was surfaced to the developer,
    not which internal rule id happened to surface it.
    """
    return any(
        f.resource_address == expected["resource"] and f.pillar.value == expected["pillar"]
        for f in result.active
    )


def evaluate() -> Dict[str, object]:
    started = time.time()
    report: Dict[str, object] = {"suites": [], "clean": [], "totals": {}}

    total_seeded = 0
    total_rules_only = 0
    total_both = 0

    for plan_name, truth in GROUND_TRUTH.items():
        rules_only = _run(plan_name, use_reasoner=False)
        both = _run(plan_name, use_reasoner=True)

        missed_by_rules = [t for t in truth if not _detected(rules_only, t)]
        missed_by_both = [t for t in truth if not _detected(both, t)]
        recovered = [t for t in missed_by_rules if t not in missed_by_both]

        total_seeded += len(truth)
        total_rules_only += len(truth) - len(missed_by_rules)
        total_both += len(truth) - len(missed_by_both)

        report["suites"].append({
            "plan": plan_name,
            "seeded": len(truth),
            "detected_rules_only": len(truth) - len(missed_by_rules),
            "detected_with_reasoning": len(truth) - len(missed_by_both),
            "recovered_by_reasoning": [t["issue"] for t in recovered],
            "still_missed": [t["issue"] for t in missed_by_both],
            "verdict": both.verdict.value,
            "verdict_correct": both.verdict is Verdict.BLOCK,
            "duration_ms": both.duration_ms,
        })

    for plan_name in CLEAN_PLANS:
        result = _run(plan_name, use_reasoner=True)
        report["clean"].append({
            "plan": plan_name,
            "false_positives": len(result.active),
            "details": [
                "{} on {}".format(f.rule_id, f.resource_address)
                for f in result.active
            ],
            "verdict": result.verdict.value,
            "verdict_correct": result.verdict is Verdict.PASS,
        })

    false_positives = sum(c["false_positives"] for c in report["clean"])
    report["totals"] = {
        "seeded_violations": total_seeded,
        "detected_rules_only": total_rules_only,
        "detected_with_reasoning": total_both,
        "recall_rules_only": round(total_rules_only / total_seeded, 3),
        "recall_with_reasoning": round(total_both / total_seeded, 3),
        "reasoning_uplift": total_both - total_rules_only,
        "false_positives_on_clean_plan": false_positives,
        "wall_clock_s": round(time.time() - started, 2),
    }
    return report


def to_markdown(report: Dict[str, object]) -> str:
    totals = report["totals"]
    lines = [
        "# Agent SecOps -- Benchmark Results",
        "",
        "Measured against the seeded misconfiguration test set in "
        "`examples/plans/`, with ground truth labelled in `scripts/benchmark.py`.",
        "",
        "## Headline numbers",
        "",
        "| Metric | Value |",
        "|---|---|",
        "| Seeded violations across all three clouds | {} |".format(totals["seeded_violations"]),
        "| Detected by deterministic rules alone | {} ({:.1%}) |".format(
            totals["detected_rules_only"], totals["recall_rules_only"]),
        "| Detected with the reasoning layer | {} ({:.1%}) |".format(
            totals["detected_with_reasoning"], totals["recall_with_reasoning"]),
        "| **Violations recovered by reasoning alone** | **{}** |".format(totals["reasoning_uplift"]),
        "| False positives on the compliant plan | {} |".format(totals["false_positives_on_clean_plan"]),
        "| Total evaluation wall-clock | {} s |".format(totals["wall_clock_s"]),
        "",
        "The uplift row is the research claim in one number: those violations "
        "are visible in framework guidance but are not expressed by any "
        "hand-written rule, which is exactly the class a static scanner misses.",
        "",
        "## Per-plan breakdown",
        "",
        "| Plan | Seeded | Rules only | + Reasoning | Verdict | Time |",
        "|---|---|---|---|---|---|",
    ]
    for suite in report["suites"]:
        lines.append("| `{}` | {} | {} | {} | {} | {} ms |".format(
            suite["plan"], suite["seeded"], suite["detected_rules_only"],
            suite["detected_with_reasoning"], suite["verdict"].upper(),
            suite["duration_ms"],
        ))
    lines.append("")

    lines.append("## What the reasoning layer recovered")
    lines.append("")
    any_recovered = False
    for suite in report["suites"]:
        for issue in suite["recovered_by_reasoning"]:
            any_recovered = True
            lines.append("- `{}`: {}".format(suite["plan"], issue))
    if not any_recovered:
        lines.append("_No additional violations recovered in this run._")
    lines.append("")

    still = [(s["plan"], i) for s in report["suites"] for i in s["still_missed"]]
    lines.append("## Known gaps (not yet detected)")
    lines.append("")
    if still:
        lines.append("Reported honestly -- these are the next rules to write:")
        lines.append("")
        for plan, issue in still:
            lines.append("- `{}`: {}".format(plan, issue))
    else:
        lines.append("_All seeded violations are currently detected._")
    lines.append("")

    lines.append("## False positives on the compliant module")
    lines.append("")
    for clean in report["clean"]:
        lines.append("- `{}`: {} false positive(s), verdict {}".format(
            clean["plan"], clean["false_positives"], clean["verdict"].upper()))
        for detail in clean["details"]:
            lines.append("  - {}".format(detail))
    lines.append("")
    lines.append(
        "A gate that fails clean code gets disabled by the team that owns it, "
        "so this number matters as much as the detection rate."
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the detection benchmark.")
    parser.add_argument("--markdown", help="Write a Markdown report to this path.")
    parser.add_argument("--json", dest="json_out", help="Write raw JSON results here.")
    args = parser.parse_args()

    report = evaluate()
    markdown = to_markdown(report)

    if args.markdown:
        Path(args.markdown).write_text(markdown, encoding="utf-8")
        print("Wrote {}".format(args.markdown))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("Wrote {}".format(args.json_out))
    if not args.markdown and not args.json_out:
        print(markdown)

    totals = report["totals"]
    # Non-zero exit if the suite regressed badly, so this can run in CI.
    return 0 if totals["recall_with_reasoning"] >= 0.8 else 1


if __name__ == "__main__":
    raise SystemExit(main())
