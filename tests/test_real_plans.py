"""Regression tests for real `terraform show -json` output and review fixes.

The fixtures in examples/plans/ are hand-written. The plans in
examples/plans/real/ were produced by terraform itself from the seeded
modules, so they carry the shapes real plans have: null for every unset
attribute, nested blocks, split AWS bucket resources, and a `configuration`
section with the dependency graph.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from agent.cli import main
from agent.config import Policy, Waiver, load_policy
from agent.engine import evaluate_file, evaluate_plan
from agent.models import Action, Resource, Severity, Verdict
from agent.plan_parser import classify, detect_provider, load_plan, parse_plan
from agent.report import render_sarif
from agent.rules.base import all_rules
from scripts.benchmark import GROUND_TRUTH, evaluate

ROOT = Path(__file__).resolve().parent.parent
REAL = ROOT / "examples" / "plans" / "real"
POLICY = ROOT / "policies" / "policy.yaml"


def resource(rtype, referenced=(), **after):
    return Resource(
        address="{}.test".format(rtype),
        type=rtype,
        name="test",
        provider=detect_provider(rtype),
        kind=classify(rtype),
        action=Action.CREATE,
        after=dict(after),
        referenced_attrs=list(referenced),
    )


def fire(rule_id, res):
    rule = next(r for r in all_rules() if r.id == rule_id)
    return rule.evaluate(res)


# --- real plans ----------------------------------------------------------

@pytest.mark.parametrize("name", sorted(GROUND_TRUTH))
def test_real_seeded_plans_are_blocked(name):
    assert evaluate_file(str(REAL / name), str(POLICY)).verdict is Verdict.BLOCK


def test_real_compliant_plan_passes():
    result = evaluate_file(str(REAL / "azure_compliant.plan.json"), str(POLICY))
    assert result.verdict is Verdict.PASS
    assert all(f.severity.rank < Severity.MEDIUM.rank for f in result.active)


def test_benchmark_detects_every_seeded_violation_in_real_plans():
    report = evaluate()
    for data in (report, report["real"]):
        missed = [i for s in data["suites"] for i in s["still_missed"]]
        assert missed == []
        assert data["totals"]["false_positives_on_clean_plan"] == 0


def test_real_plan_has_dependency_edges():
    plan = load_plan(REAL / "azure_noncompliant.plan.json")
    assert "azurerm_mssql_server.db" in plan.edges["azurerm_mssql_firewall_rule.allow_all"]


# --- parser ----------------------------------------------------------------

def _plan_with_config(resource_changes, config_resources):
    return {
        "resource_changes": resource_changes,
        "configuration": {"root_module": {"resources": config_resources}},
    }


def test_edges_survive_count_indexes():
    data = _plan_with_config(
        [
            {"address": "aws_s3_bucket.b[0]", "type": "aws_s3_bucket", "name": "b",
             "change": {"actions": ["create"], "after": {}}},
            {"address": "aws_s3_bucket_acl.a[0]", "type": "aws_s3_bucket_acl", "name": "a",
             "change": {"actions": ["create"], "after": {"acl": "public-read"}}},
        ],
        [
            {"address": "aws_s3_bucket.b", "expressions": {}},
            {"address": "aws_s3_bucket_acl.a",
             "expressions": {"bucket": {"references": ["aws_s3_bucket.b[0].id", "aws_s3_bucket.b[0]"]}}},
        ],
    )
    plan = parse_plan(data)
    assert plan.edges["aws_s3_bucket_acl.a[0]"] == ["aws_s3_bucket.b[0]"]


def test_s3_acl_is_folded_onto_the_bucket():
    plan = load_plan(REAL / "aws_noncompliant.plan.json")
    result = evaluate_plan(plan, load_policy(str(POLICY)))
    on_bucket = {f.rule_id for f in result.active if f.resource_address == "aws_s3_bucket.data"}
    assert "WAF-SEC-003" in on_bucket
    # The attachment resources themselves are not judged as buckets.
    assert not [f for f in result.active if f.resource_address.startswith("aws_s3_bucket_")]


def test_global_gcp_firewall_does_not_inherit_a_region():
    plan = load_plan(REAL / "gcp_noncompliant.plan.json")
    fw = next(r for r in plan.resources if r.type == "google_compute_firewall")
    assert "region" not in fw.after


# --- rules -----------------------------------------------------------------

def test_region_match_is_exact():
    assert fire("CAF-LZ-001", resource("azurerm_resource_group", location="eastus2")) is not None
    assert fire("CAF-LZ-001", resource("azurerm_resource_group", location="eastus")) is None
    assert fire("CAF-LZ-001", resource("aws_instance", availability_zone="us-east-1a")) is None


def test_internet_service_tag_is_open_ingress():
    res = resource("azurerm_network_security_rule", direction="Inbound", access="Allow",
                   source_address_prefix="Internet", destination_port_range="3389")
    assert fire("WAF-SEC-004", res) is not None


def test_port_range_covering_ssh_is_caught():
    res = resource("aws_security_group", ingress=[
        {"from_port": 20, "to_port": 25, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"]}])
    assert "22" in fire("WAF-SEC-004", res).explanation


def test_all_traffic_rule_is_caught():
    res = resource("aws_security_group", ingress=[
        {"from_port": 0, "to_port": 0, "protocol": "-1", "cidr_blocks": ["0.0.0.0/0"]}])
    assert "every port" in fire("WAF-SEC-004", res).explanation


def test_egress_rule_is_not_ingress():
    res = resource("aws_security_group_rule", type="egress", from_port=22, to_port=22,
                   protocol="tcp", cidr_blocks=["0.0.0.0/0"])
    assert fire("WAF-SEC-004", res) is None


def test_inline_nsg_security_rule_is_checked():
    res = resource("azurerm_network_security_group", security_rule=[
        {"direction": "Inbound", "access": "Allow", "source_address_prefix": "*",
         "destination_port_range": "22"}])
    assert fire("WAF-SEC-004", res) is not None


def test_referenced_password_is_not_hardcoded():
    literal = resource("azurerm_mssql_server", administrator_login_password="x")
    from_vault = resource("azurerm_mssql_server", referenced=["administrator_login_password"],
                          administrator_login_password="x")
    assert fire("WAF-SEC-006", literal) is not None
    assert fire("WAF-SEC-006", from_vault) is None


def test_default_infrastructure_encryption_is_not_misreported():
    res = resource("azurerm_storage_account", infrastructure_encryption_enabled=False,
                   customer_managed_key=[{"key_vault_key_id": "k"}])
    assert fire("WAF-SEC-005", res) is None


def test_backup_retention_on_real_shapes():
    azure = resource("azurerm_mssql_database",
                     short_term_retention_policy=[{"retention_days": 1}])
    gcp = resource("google_sql_database_instance",
                   settings=[{"backup_configuration": [{"enabled": False}]}])
    assert fire("WAF-REL-002", azure) is not None
    assert fire("WAF-REL-002", gcp) is not None


# --- engine ----------------------------------------------------------------

def test_policy_overrides_do_not_leak_between_runs():
    plan_path = ROOT / "examples" / "plans" / "azure_noncompliant.plan.json"
    lowered = load_policy(str(POLICY))
    lowered.rule_overrides = {"WAF-SEC-001": {"severity": "info"}}
    evaluate_plan(load_plan(plan_path), lowered)
    result = evaluate_plan(load_plan(plan_path), load_policy(str(POLICY)))
    f = next(f for f in result.findings if f.rule_id == "WAF-SEC-001")
    assert f.severity is Severity.HIGH


def test_waived_exposure_does_not_feed_the_graph():
    plan_path = REAL / "aws_noncompliant.plan.json"
    base = evaluate_plan(load_plan(plan_path), load_policy(str(POLICY)))
    assert any(f.rule_id == "REASON-GRAPH" for f in base.findings)

    policy = load_policy(str(POLICY))
    policy.waivers = [Waiver(rule_id="WAF-SEC-004", reason="test")]
    waived = evaluate_plan(load_plan(plan_path), policy)
    graph = [f for f in waived.findings if f.rule_id == "REASON-GRAPH"]
    assert all("aws_security_group.web" not in f.explanation for f in graph)


# --- reports and CLI ---------------------------------------------------------

def test_sarif_keeps_reasoning_probes_distinct():
    import json

    result = evaluate_file(str(ROOT / "examples" / "plans" / "azure_noncompliant.plan.json"),
                           str(POLICY))
    rules = json.loads(render_sarif(result))["runs"][0]["tool"]["driver"]["rules"]
    ids = [r["id"] for r in rules]
    assert len(ids) == len(set(ids))
    assert sum(i.startswith("REASON-OFFLINE/") for i in ids) > 1


def test_cli_usage_error_is_not_a_block():
    assert main(["evaluate", "--plan", "x.json", "--no-such-flag"]) == 3
