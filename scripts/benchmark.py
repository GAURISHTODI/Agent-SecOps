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

Each number is measured twice: on the hand-written fixtures in
`examples/plans/`, and on genuine `terraform show -json` output from the
seeded modules in `examples/terraform/`, saved in `examples/plans/real/`.
The second set is what the CI pipeline actually feeds the gate.

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
REAL_PLANS = PLANS / "real"
POLICY = ROOT / "policies" / "policy.yaml"

# Titles of the offline reasoning probes, so ground truth can name them the
# same way it names a rule id.
NET_ALLOW = "Data service has no network allow-list (open default action)"
SHARED_KEYS = "Shared access keys left enabled where identity-based auth would do"
VERSIONING = "Irreplaceable data stored without versioning"
FIREWALL_ALL = "Database firewall rule spans the entire IPv4 range"
VM_PASSWORD = "Virtual machine allows password authentication"
VM_ZONE = "Single instance with no availability construct"
KV_RBAC = "Key vault uses legacy access policies instead of RBAC"

# The ground truth. Each entry is a violation deliberately seeded into the
# module, labelled with the resource it lives on, the pillar it breaks, and
# the rule id or reasoning probe that should report it. A violation counts as
# detected only when that specific check fires on that specific resource --
# another finding that merely shares the pillar does not count.
GROUND_TRUTH: Dict[str, List[Dict[str, object]]] = {
    "azure_noncompliant.plan.json": [
        {"resource": "azurerm_resource_group.rg", "issue": "unapproved region", "pillar": "CAF:LandingZone", "match": ["CAF-LZ-001"]},
        {"resource": "azurerm_resource_group.rg", "issue": "missing governance tags", "pillar": "CAF:Governance", "match": ["CAF-GOV-001"]},
        {"resource": "azurerm_storage_account.data", "issue": "http allowed", "pillar": "WAF:Security", "match": ["WAF-SEC-001"]},
        {"resource": "azurerm_storage_account.data", "issue": "TLS 1.0", "pillar": "WAF:Security", "match": ["WAF-SEC-002"]},
        {"resource": "azurerm_storage_account.data", "issue": "anonymous blob access", "pillar": "WAF:Security", "match": ["WAF-SEC-003"]},
        {"resource": "azurerm_storage_account.data", "issue": "LRS replication", "pillar": "WAF:Reliability", "match": ["WAF-REL-001"]},
        {"resource": "azurerm_storage_account.data", "issue": "public network access", "pillar": "CAF:LandingZone", "match": ["CAF-LZ-002"]},
        {"resource": "azurerm_storage_account.data", "issue": "network default allow", "pillar": "CAF:LandingZone", "match": [NET_ALLOW]},
        {"resource": "azurerm_storage_account.data", "issue": "shared keys enabled", "pillar": "WAF:Security", "match": [SHARED_KEYS]},
        {"resource": "azurerm_storage_account.data", "issue": "versioning disabled", "pillar": "WAF:Reliability", "match": [VERSIONING]},
        {"resource": "azurerm_storage_account.data", "issue": "hot tier for archive data", "pillar": "WAF:Sustainability", "match": ["WAF-SUS-001"]},
        {"resource": "azurerm_mssql_server.db", "issue": "hardcoded password", "pillar": "WAF:Security", "match": ["WAF-SEC-006"]},
        {"resource": "azurerm_mssql_server.db", "issue": "TLS 1.0", "pillar": "WAF:Security", "match": ["WAF-SEC-002"]},
        {"resource": "azurerm_mssql_database.db", "issue": "1-day backup retention", "pillar": "WAF:Reliability", "match": ["WAF-REL-002"]},
        {"resource": "azurerm_mssql_server.db", "issue": "public network access", "pillar": "CAF:LandingZone", "match": ["CAF-LZ-002"]},
        {"resource": "azurerm_mssql_firewall_rule.allow_all", "issue": "firewall spans all IPv4", "pillar": "WAF:Security", "match": [FIREWALL_ALL]},
        {"resource": "azurerm_network_security_rule.ssh", "issue": "ssh open to internet", "pillar": "WAF:Security", "match": ["WAF-SEC-004"]},
        {"resource": "azurerm_linux_virtual_machine.app", "issue": "hardcoded password", "pillar": "WAF:Security", "match": ["WAF-SEC-006"]},
        {"resource": "azurerm_linux_virtual_machine.app", "issue": "password auth enabled", "pillar": "WAF:Security", "match": [VM_PASSWORD]},
        {"resource": "azurerm_linux_virtual_machine.app", "issue": "premium SKU in dev", "pillar": "WAF:CostOptimization", "match": ["WAF-COST-001"]},
        {"resource": "azurerm_linux_virtual_machine.app", "issue": "no availability zone", "pillar": "WAF:Reliability", "match": [VM_ZONE]},
        {"resource": "azurerm_linux_virtual_machine.app", "issue": "no cost centre tag", "pillar": "CAF:CostManagement", "match": ["CAF-COST-001"]},
        {"resource": "azurerm_role_assignment.app_owner", "issue": "Owner at subscription scope", "pillar": "CAF:Identity", "match": ["CAF-IAM-001"]},
        {"resource": "azurerm_key_vault.kv", "issue": "purge protection off", "pillar": "WAF:Reliability", "match": ["WAF-REL-003"]},
        {"resource": "azurerm_key_vault.kv", "issue": "access policies not RBAC", "pillar": "CAF:Identity", "match": [KV_RBAC]},
        {"resource": "azurerm_key_vault.kv", "issue": "public network access", "pillar": "CAF:LandingZone", "match": ["CAF-LZ-002"]},
        {"resource": "azurerm_public_ip.edge", "issue": "unjustified public exposure", "pillar": "CAF:LandingZone", "match": ["CAF-LZ-003"]},
        {"resource": "azurerm_public_ip.edge", "issue": "static IP idle in dev", "pillar": "WAF:CostOptimization", "match": ["WAF-COST-002"]},
    ],
    "aws_noncompliant.plan.json": [
        {"resource": "aws_s3_bucket.data", "issue": "public-read ACL", "pillar": "WAF:Security", "match": ["WAF-SEC-003"]},
        {"resource": "aws_s3_bucket.data", "issue": "versioning disabled", "pillar": "WAF:Reliability", "match": [VERSIONING]},
        {"resource": "aws_s3_bucket.data", "issue": "unapproved region", "pillar": "CAF:LandingZone", "match": ["CAF-LZ-001"]},
        {"resource": "aws_security_group.web", "issue": "ssh + postgres open to internet", "pillar": "WAF:Security", "match": ["WAF-SEC-004"]},
        {"resource": "aws_db_instance.main", "issue": "hardcoded password", "pillar": "WAF:Security", "match": ["WAF-SEC-006"]},
        {"resource": "aws_db_instance.main", "issue": "zero backup retention", "pillar": "WAF:Reliability", "match": ["WAF-REL-002"]},
        {"resource": "aws_db_instance.main", "issue": "skip final snapshot", "pillar": "WAF:OperationalExcellence", "match": ["WAF-OPS-002"]},
        {"resource": "aws_iam_role_policy.admin", "issue": "wildcard actions", "pillar": "CAF:Identity", "match": ["CAF-IAM-001"]},
    ],
    "gcp_noncompliant.plan.json": [
        {"resource": "google_storage_bucket.data", "issue": "unapproved region", "pillar": "CAF:LandingZone", "match": ["CAF-LZ-001"]},
        {"resource": "google_storage_bucket.data", "issue": "versioning disabled", "pillar": "WAF:Reliability", "match": [VERSIONING]},
        {"resource": "google_compute_firewall.allow_ssh", "issue": "ssh/rdp open to internet", "pillar": "WAF:Security", "match": ["WAF-SEC-004"]},
        {"resource": "google_sql_database_instance.main", "issue": "hardcoded password", "pillar": "WAF:Security", "match": ["WAF-SEC-006"]},
        {"resource": "google_sql_database_instance.main", "issue": "backups disabled", "pillar": "WAF:Reliability", "match": ["WAF-REL-002"]},
        {"resource": "google_project_iam_member.owner", "issue": "roles/owner granted", "pillar": "CAF:Identity", "match": ["CAF-IAM-001"]},
    ],
}

CLEAN_PLANS = ["azure_compliant.plan.json"]


def _run(plan_path: Path, use_reasoner: bool) -> GateResult:
    policy = load_policy(str(POLICY))
    if not use_reasoner:
        policy.reasoner = ReasonerConfig(provider="none", enabled=False)
    return evaluate_plan(load_plan(str(plan_path)), policy)


def _detected(result: GateResult, expected: Dict[str, object]) -> bool:
    """Did the named check fire on the named resource?"""
    names = set(expected["match"])  # type: ignore[arg-type]
    return any(
        f.resource_address == expected["resource"]
        and (f.rule_id in names or f.title in names)
        for f in result.active
    )


def _evaluate_set(directory: Path) -> Dict[str, object]:
    report: Dict[str, object] = {"suites": [], "clean": [], "totals": {}}
    total_seeded = 0
    total_rules_only = 0
    total_both = 0

    for plan_name, truth in GROUND_TRUTH.items():
        rules_only = _run(directory / plan_name, use_reasoner=False)
        both = _run(directory / plan_name, use_reasoner=True)

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

    remediate_at = load_policy(str(POLICY)).remediate_at
    for plan_name in CLEAN_PLANS:
        result = _run(directory / plan_name, use_reasoner=True)
        # A false positive is a finding that changes the verdict on clean
        # code. Low-severity advisories are listed too, but they do not stop
        # or flag a deployment.
        blocking = [f for f in result.active if f.severity.rank >= remediate_at.rank]
        advisory = [f for f in result.active if f.severity.rank < remediate_at.rank]
        report["clean"].append({
            "plan": plan_name,
            "false_positives": len(blocking),
            "advisories": len(advisory),
            "details": [
                "{} on {} ({})".format(f.rule_id, f.resource_address, f.severity.value)
                for f in result.active
            ],
            "verdict": result.verdict.value,
            "verdict_correct": result.verdict is Verdict.PASS,
        })

    report["totals"] = {
        "seeded_violations": total_seeded,
        "detected_rules_only": total_rules_only,
        "detected_with_reasoning": total_both,
        "recall_rules_only": round(total_rules_only / total_seeded, 3),
        "recall_with_reasoning": round(total_both / total_seeded, 3),
        "reasoning_uplift": total_both - total_rules_only,
        "false_positives_on_clean_plan": sum(c["false_positives"] for c in report["clean"]),
        "advisories_on_clean_plan": sum(c["advisories"] for c in report["clean"]),
    }
    return report


def evaluate() -> Dict[str, object]:
    """Score the hand-written fixtures; real plans are under `real`.

    The top-level keys describe the fixture set (the dashboard reads them);
    `real` has the same shape for genuine terraform output.
    """
    started = time.time()
    report = _evaluate_set(PLANS)
    if all((REAL_PLANS / name).is_file() for name in [*GROUND_TRUTH, *CLEAN_PLANS]):
        report["real"] = _evaluate_set(REAL_PLANS)
    report["totals"]["wall_clock_s"] = round(time.time() - started, 2)
    return report


def _section(title: str, intro: str, data: Dict[str, object]) -> List[str]:
    totals = data["totals"]
    lines = [
        "## {}".format(title),
        "",
        intro,
        "",
        "| Metric | Value |",
        "|---|---|",
        "| Seeded violations across all three clouds | {} |".format(totals["seeded_violations"]),
        "| Detected by deterministic rules alone | {} ({:.1%}) |".format(
            totals["detected_rules_only"], totals["recall_rules_only"]),
        "| Detected with the reasoning layer | {} ({:.1%}) |".format(
            totals["detected_with_reasoning"], totals["recall_with_reasoning"]),
        "| **Violations recovered by reasoning alone** | **{}** |".format(totals["reasoning_uplift"]),
        "| False positives on the compliant plan (verdict-affecting) | {} |".format(
            totals["false_positives_on_clean_plan"]),
        "| Low-severity advisories on the compliant plan | {} |".format(
            totals["advisories_on_clean_plan"]),
        "",
        "| Plan | Seeded | Rules only | + Reasoning | Verdict | Time |",
        "|---|---|---|---|---|---|",
    ]
    for suite in data["suites"]:
        lines.append("| `{}` | {} | {} | {} | {} | {} ms |".format(
            suite["plan"], suite["seeded"], suite["detected_rules_only"],
            suite["detected_with_reasoning"], suite["verdict"].upper(),
            suite["duration_ms"],
        ))
    lines.append("")

    lines.append("**Recovered by the reasoning layer:**")
    lines.append("")
    recovered = [(s["plan"], i) for s in data["suites"] for i in s["recovered_by_reasoning"]]
    for plan, issue in recovered:
        lines.append("- `{}`: {}".format(plan, issue))
    if not recovered:
        lines.append("_None in this run._")
    lines.append("")

    lines.append("**Known gaps (not yet detected):**")
    lines.append("")
    still = [(s["plan"], i) for s in data["suites"] for i in s["still_missed"]]
    for plan, issue in still:
        lines.append("- `{}`: {}".format(plan, issue))
    if not still:
        lines.append("_All seeded violations are currently detected._")
    lines.append("")

    lines.append("**Compliant module:**")
    lines.append("")
    for clean in data["clean"]:
        lines.append("- `{}`: verdict {}, {} verdict-affecting false positive(s), "
                     "{} low-severity advisory finding(s)".format(
                         clean["plan"], clean["verdict"].upper(),
                         clean["false_positives"], clean["advisories"]))
        for detail in clean["details"]:
            lines.append("  - {}".format(detail))
    lines.append("")
    return lines


def to_markdown(report: Dict[str, object]) -> str:
    lines = [
        "# Agent SecOps -- Benchmark Results",
        "",
        "Ground truth is labelled in `scripts/benchmark.py`. A seeded violation "
        "counts as detected only when the specific rule or reasoning probe named "
        "for it fires on the right resource.",
        "",
    ]
    lines += _section(
        "Hand-written fixtures",
        "Plans in `examples/plans/`, written by hand to mirror the seeded modules.",
        report,
    )
    if "real" in report:
        lines += _section(
            "Real terraform plan output",
            "Plans in `examples/plans/real/`, produced by `terraform plan` + "
            "`terraform show -json` on the seeded modules in `examples/terraform/` "
            "and the compliant module in `infra/demo/`. This is the input shape "
            "the CI pipeline gives the gate.",
            report["real"],  # type: ignore[arg-type]
        )
    lines += [
        "## Reading these numbers",
        "",
        "- The offline reasoning layer is a set of deterministic, hand-written "
        "probes derived from the framework knowledge base. \"Recovered by "
        "reasoning\" therefore means \"caught by a framework-intent probe that "
        "no Layer-1 rule implements\", not \"discovered by a language model\".",
        "- The seeded modules were written by the same team that wrote the "
        "rules and probes, so recall on them is an upper bound. An independent "
        "test set is the obvious next step.",
        "- Total evaluation wall-clock: {} s.".format(report["totals"]["wall_clock_s"]),
        "",
    ]
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
