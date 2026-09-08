"""End-to-end gate behaviour: verdicts, waivers, thresholds, exit codes."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from agent.cli import main
from agent.config import Policy, ReasonerConfig, Waiver, load_policy
from agent.engine import evaluate_file, evaluate_plan
from agent.models import Severity, Verdict
from agent.plan_parser import load_plan
from agent.report import render_json, render_markdown, render_sarif

ROOT = Path(__file__).resolve().parent.parent
PLANS = ROOT / "examples" / "plans"
POLICY = ROOT / "policies" / "policy.yaml"


def _result(name):
    return evaluate_file(str(PLANS / name), str(POLICY))


# --- the headline demonstration ---------------------------------------

def test_compliant_plan_passes_cleanly():
    result = _result("azure_compliant.plan.json")
    assert result.verdict is Verdict.PASS
    assert result.active == [], [f.title for f in result.active]


def test_noncompliant_plan_is_blocked():
    result = _result("azure_noncompliant.plan.json")
    assert result.verdict is Verdict.BLOCK
    assert len(result.active) > 20


@pytest.mark.parametrize("plan", [
    "aws_noncompliant.plan.json",
    "gcp_noncompliant.plan.json",
])
def test_gate_logic_is_cloud_agnostic(plan):
    """Same rules, same verdict logic, different cloud."""
    result = _result(plan)
    assert result.verdict is Verdict.BLOCK
    assert any(f.pillar.framework == "CAF" for f in result.active)
    assert any(f.pillar.framework == "WAF" for f in result.active)


def test_seeded_violations_are_each_caught():
    """Every misconfiguration seeded into the fixture must be detected."""
    result = _result("azure_noncompliant.plan.json")
    caught = {f.rule_id for f in result.active}
    expected = {
        "WAF-SEC-001",   # http allowed
        "WAF-SEC-002",   # TLS 1.0
        "WAF-SEC-003",   # public blob
        "WAF-SEC-004",   # ssh from internet
        "WAF-SEC-006",   # hardcoded password
        "WAF-REL-001",   # LRS
        "WAF-REL-002",   # 1-day backups
        "WAF-REL-003",   # no purge protection
        "CAF-GOV-001",   # missing tags
        "CAF-LZ-001",    # unapproved region
        "CAF-LZ-002",    # public network access
        "CAF-IAM-001",   # Owner at subscription scope
        "WAF-COST-001",  # premium SKU in dev
    }
    assert expected <= caught, "missed: {}".format(sorted(expected - caught))


def test_both_layers_contribute():
    """The research claim: reasoning adds findings the rules did not make."""
    result = _result("azure_noncompliant.plan.json")
    assert result.stats["findings_from_rules"] > 0
    assert result.stats["findings_from_reasoner"] > 0


def test_reasoner_never_duplicates_a_rule_finding():
    result = _result("azure_noncompliant.plan.json")
    by_resource = {}
    for f in result.findings:
        by_resource.setdefault(f.resource_address, {"rules": set(), "reason": set()})
        key = "rules" if f.source == "rules" else "reason"
        by_resource[f.resource_address][key].add(f.title.lower())
    for address, sides in by_resource.items():
        overlap = sides["rules"] & sides["reason"]
        assert not overlap, "{} duplicated: {}".format(address, overlap)


# --- policy behaviour --------------------------------------------------

def test_waiver_suppresses_and_records():
    plan = load_plan(str(PLANS / "azure_noncompliant.plan.json"))
    policy = Policy(
        waivers=[Waiver(rule_id="WAF-SEC-003", resource="*",
                        reason="accepted for the public docs bucket",
                        expires="2099-01-01")],
        reasoner=ReasonerConfig(provider="none", enabled=False),
    )
    result = evaluate_plan(plan, policy)
    waived = [f for f in result.findings if f.rule_id == "WAF-SEC-003"]
    assert waived and all(f.waived for f in waived)
    assert all(f.waiver_reason for f in waived)
    assert all(f.rule_id != "WAF-SEC-003" for f in result.active)


def test_expired_waiver_stops_suppressing():
    yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    plan = load_plan(str(PLANS / "azure_noncompliant.plan.json"))
    policy = Policy(
        waivers=[Waiver(rule_id="WAF-SEC-003", expires=yesterday)],
        reasoner=ReasonerConfig(provider="none", enabled=False),
    )
    result = evaluate_plan(plan, policy)
    assert any(f.rule_id == "WAF-SEC-003" for f in result.active)
    assert "WAF-SEC-003" in result.stats["expired_waivers"]


def test_threshold_changes_the_verdict():
    plan = load_plan(str(PLANS / "azure_compliant.plan.json"))
    strict = Policy(
        block_at=Severity.LOW,
        remediate_at=Severity.INFO,
        reasoner=ReasonerConfig(provider="none", enabled=False),
    )
    assert evaluate_plan(plan, strict).verdict is Verdict.PASS  # genuinely clean

    noncompliant = load_plan(str(PLANS / "azure_noncompliant.plan.json"))
    lenient = Policy(
        block_at=Severity.CRITICAL,
        remediate_at=Severity.CRITICAL,
        reasoner=ReasonerConfig(provider="none", enabled=False),
    )
    assert evaluate_plan(noncompliant, lenient).verdict is Verdict.BLOCK


def test_reasoner_findings_are_advisory_by_default():
    """An LLM must not be able to fail a build unless the org opts in."""
    plan = load_plan(str(PLANS / "azure_compliant.plan.json"))
    policy = Policy(fail_on_reasoner_findings=False)
    result = evaluate_plan(plan, policy)
    assert result.verdict is not Verdict.BLOCK


def test_disabling_a_rule_removes_its_findings():
    plan = load_plan(str(PLANS / "azure_noncompliant.plan.json"))
    policy = Policy(
        rule_overrides={"CAF-LZ-001": {"enabled": False}},
        reasoner=ReasonerConfig(provider="none", enabled=False),
    )
    result = evaluate_plan(plan, policy)
    assert all(f.rule_id != "CAF-LZ-001" for f in result.findings)


def test_rule_params_are_overridable_from_policy():
    plan = load_plan(str(PLANS / "azure_noncompliant.plan.json"))
    policy = Policy(
        rule_overrides={"CAF-LZ-001": {"params": {"approved": ["brazilsouth"]}}},
        reasoner=ReasonerConfig(provider="none", enabled=False),
    )
    result = evaluate_plan(plan, policy)
    assert all(f.rule_id != "CAF-LZ-001" for f in result.findings)


def test_policy_file_loads():
    policy = load_policy(str(POLICY))
    assert policy.block_at is Severity.HIGH
    assert policy.reasoner.provider in ("offline", "azure_openai", "anthropic", "none")
    assert policy.reasoner.max_resources <= 25, "cost cap must stay small"


# --- reporting ---------------------------------------------------------

def test_markdown_report_names_pillar_and_fix():
    result = _result("azure_noncompliant.plan.json")
    md = render_markdown(result)
    assert "Verdict: BLOCK" in md
    assert "WAF:Security" in md
    assert "```hcl" in md          # actionable remediation, not just a flag
    assert "Violations by framework pillar" in md


def test_markdown_report_on_pass_is_clean():
    md = render_markdown(_result("azure_compliant.plan.json"))
    assert "Verdict: PASS" in md
    assert "No CAF or WAF violations" in md


def test_json_report_is_machine_readable():
    payload = json.loads(render_json(_result("azure_noncompliant.plan.json")))
    assert payload["verdict"] == "block"
    assert payload["findings"]
    for finding in payload["findings"]:
        assert finding["pillar"]
        assert finding["framework"] in ("CAF", "WAF")
        assert 0.0 <= finding["confidence"] <= 1.0


def test_sarif_is_valid_shape():
    payload = json.loads(render_sarif(_result("azure_noncompliant.plan.json")))
    assert payload["version"] == "2.1.0"
    run = payload["runs"][0]
    assert run["tool"]["driver"]["rules"]
    assert all(r["level"] in ("error", "warning", "note") for r in run["results"])


# --- CLI contract ------------------------------------------------------

def test_cli_exit_codes_gate_the_pipeline(tmp_path):
    assert main(["evaluate", "--plan", str(PLANS / "azure_compliant.plan.json"),
                 "--policy", str(POLICY)]) == 0
    assert main(["evaluate", "--plan", str(PLANS / "azure_noncompliant.plan.json"),
                 "--policy", str(POLICY)]) == 2


def test_cli_soft_fail_never_blocks():
    assert main(["evaluate", "--plan", str(PLANS / "azure_noncompliant.plan.json"),
                 "--policy", str(POLICY), "--soft-fail"]) == 0


def test_cli_writes_all_three_report_formats(tmp_path):
    md, js, sarif = tmp_path / "r.md", tmp_path / "r.json", tmp_path / "r.sarif"
    main(["evaluate", "--plan", str(PLANS / "azure_noncompliant.plan.json"),
          "--policy", str(POLICY), "--markdown", str(md),
          "--json", str(js), "--sarif", str(sarif)])
    assert md.read_text(encoding="utf-8").startswith("## Agent SecOps")
    assert json.loads(js.read_text(encoding="utf-8"))["verdict"] == "block"
    assert json.loads(sarif.read_text(encoding="utf-8"))["version"] == "2.1.0"


def test_cli_reports_bad_plan_without_crashing(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    assert main(["evaluate", "--plan", str(bad)]) == 3


def test_gate_never_crashes_on_malformed_attributes():
    """Defence in depth: a weird plan must produce a verdict, not a traceback."""
    from agent.plan_parser import parse_plan

    plan = parse_plan({
        "resource_changes": [{
            "address": "azurerm_storage_account.weird",
            "type": "azurerm_storage_account",
            "name": "weird",
            "change": {
                "actions": ["create"],
                "after": {
                    "min_tls_version": {"unexpected": "object"},
                    "tags": "not-a-dict",
                    "network_rules": "also-not-a-list",
                    "backup_retention_days": "seven",
                },
            },
        }]
    })
    result = evaluate_plan(plan, Policy())
    assert result.verdict in (Verdict.PASS, Verdict.REMEDIATE, Verdict.BLOCK)
