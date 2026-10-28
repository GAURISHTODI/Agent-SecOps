"""Tests for the dependency-graph risk propagation (Layer 2b)."""
from __future__ import annotations

from agent.engine import evaluate_plan
from agent.models import Action, Finding, Pillar, Provider, Resource, Severity
from agent.plan_parser import classify, detect_provider, parse_plan
from agent.reasoner.graph import GraphReasoner


def res(rtype, name, **after):
    return Resource(
        address="{}.{}".format(rtype, name), type=rtype, name=name,
        provider=detect_provider(rtype), kind=classify(rtype),
        action=Action.CREATE, after=dict(after),
    )


def finding(address, rule_id, severity, pillar=Pillar.WAF_SECURITY, title="t"):
    return Finding(
        rule_id=rule_id, title=title or rule_id, pillar=pillar, severity=severity,
        resource_address=address, explanation="x", remediation="y", source="rules",
    )


def scenario():
    sg = res("aws_security_group", "web")
    db = res("aws_db_instance", "main", tags={"environment": "prod"})
    findings = [
        finding(sg.address, "WAF-SEC-004", Severity.CRITICAL, title="open to internet"),
        finding(db.address, "WAF-SEC-006", Severity.CRITICAL, title="plaintext password"),
        finding(db.address, "WAF-REL-002", Severity.HIGH, Pillar.WAF_RELIABILITY, "no backups"),
    ]
    return sg, db, findings


def test_exposure_propagates_along_an_edge_to_a_weak_resource():
    sg, db, findings = scenario()
    graph = GraphReasoner({db.address: [sg.address]})
    out = graph.analyse_graph([sg, db], findings)
    assert len(out) == 1
    f = out[0]
    assert f.resource_address == db.address
    assert f.rule_id == "REASON-GRAPH"
    # the explanation names the real path, source first
    assert "{} -> {}".format(sg.address, db.address) in f.explanation


def test_no_edge_means_no_compound_finding():
    sg, db, findings = scenario()
    assert GraphReasoner({}).analyse_graph([sg, db], findings) == []


def test_resource_group_hub_does_not_connect_everything():
    sg, db, findings = scenario()
    rg = res("azurerm_resource_group", "rg")
    edges = {sg.address: [rg.address], db.address: [rg.address]}
    assert GraphReasoner(edges).analyse_graph([sg, db, rg], findings) == []


def test_distance_decay_reduces_risk():
    sg, db, findings = scenario()
    mid = res("aws_subnet", "mid")
    near = GraphReasoner({db.address: [sg.address]}).analyse_graph([sg, db], findings)
    far = GraphReasoner(
        {db.address: [mid.address], mid.address: [sg.address]}
    ).analyse_graph([sg, mid, db], findings)
    assert near and far
    assert near[0].confidence > far[0].confidence


def test_a_clean_target_is_never_flagged():
    sg, db, _ = scenario()
    only_exposure = [finding(sg.address, "WAF-SEC-004", Severity.CRITICAL)]
    assert GraphReasoner({db.address: [sg.address]}).analyse_graph([sg, db], only_exposure) == []


def test_governance_findings_are_not_treated_as_weakness():
    sg, db, _ = scenario()
    noise = [
        finding(sg.address, "WAF-SEC-004", Severity.CRITICAL),
        finding(db.address, "CAF-GOV-001", Severity.MEDIUM, Pillar.CAF_GOVERNANCE),
        finding(db.address, "CAF-LZ-001", Severity.HIGH, Pillar.CAF_LANDING_ZONE),
    ]
    assert GraphReasoner({db.address: [sg.address]}).analyse_graph([sg, db], noise) == []


def test_graph_only_adds_when_the_connection_matters():
    """A resource exposed by itself is the rules' business, not the graph's."""
    db = res("aws_db_instance", "main", publicly_accessible=True)
    findings = [finding(db.address, "WAF-SEC-006", Severity.CRITICAL)]
    assert GraphReasoner({}).analyse_graph([db], findings) == []


def test_plan_parser_extracts_edges_from_configuration():
    plan = parse_plan({
        "format_version": "1.2",
        "resource_changes": [
            {"address": "aws_s3_bucket.b", "type": "aws_s3_bucket", "name": "b",
             "change": {"actions": ["create"], "after": {}}},
            {"address": "aws_s3_bucket_acl.a", "type": "aws_s3_bucket_acl", "name": "a",
             "change": {"actions": ["create"], "after": {"acl": "public-read"}}},
        ],
        "configuration": {"root_module": {"resources": [
            {"address": "aws_s3_bucket_acl.a", "expressions": {
                "bucket": {"references": ["aws_s3_bucket.b.id", "aws_s3_bucket.b"]}}},
            {"address": "aws_s3_bucket.b", "expressions": {}},
        ]}},
    })
    assert plan.edges == {"aws_s3_bucket_acl.a": ["aws_s3_bucket.b"]}


def test_engine_surfaces_graph_findings_and_stats():
    plan = parse_plan({
        "format_version": "1.2",
        "resource_changes": [
            {"address": "aws_security_group.web", "type": "aws_security_group", "name": "web",
             "change": {"actions": ["create"], "after": {
                 "ingress": [{"from_port": 22, "to_port": 22, "cidr_blocks": ["0.0.0.0/0"]}]}}},
            {"address": "aws_db_instance.main", "type": "aws_db_instance", "name": "main",
             "change": {"actions": ["create"], "after": {
                 "password": "hunter2hunter2", "backup_retention_period": 0,
                 "region": "us-east-1", "tags": {"environment": "prod", "owner": "a",
                                                  "costcenter": "c"}}}},
        ],
        "configuration": {"root_module": {"resources": [
            {"address": "aws_db_instance.main", "expressions": {
                "vpc_security_group_ids": {"references": ["aws_security_group.web.id"]}}},
            {"address": "aws_security_group.web", "expressions": {}},
        ]}},
    })
    result = evaluate_plan(plan)
    assert result.stats["graph_edges"] == 1
    assert result.stats["findings_from_graph"] == 1
    assert any(f.rule_id == "REASON-GRAPH" for f in result.findings)
    # disabling the reasoning layer disables the graph layer too
    from agent.config import ReasonerConfig, load_policy
    policy = load_policy()
    policy.reasoner = ReasonerConfig(provider="none", enabled=False)
    off = evaluate_plan(plan, policy)
    assert all(f.rule_id != "REASON-GRAPH" for f in off.findings)
