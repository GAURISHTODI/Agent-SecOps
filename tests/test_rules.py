"""Rule-level tests.

Each rule is tested in both directions -- it must fire on the violation and
stay silent on the compliant equivalent. A gate that cries wolf gets turned
off, so the negative cases matter as much as the positive ones.
"""
from __future__ import annotations

import pytest

from agent.models import Action, Kind, Provider, Resource, Severity
from agent.rules.base import all_rules


def resource(rtype="azurerm_storage_account", **after):
    from agent.plan_parser import classify, detect_provider

    return Resource(
        address="{}.test".format(rtype),
        type=rtype,
        name=after.get("name", "test"),
        provider=detect_provider(rtype),
        kind=classify(rtype),
        action=Action.CREATE,
        after=dict(after),
    )


def fire(rule_id, res):
    """Run one rule by id and return its Finding (or None)."""
    rule = next(r for r in all_rules() if r.id == rule_id)
    return rule.evaluate(res)


# --- CAF ---------------------------------------------------------------

def test_required_tags_fires_and_clears():
    assert fire("CAF-GOV-001", resource(name="a", tags={"owner": "x"})) is not None
    ok = resource(name="a", tags={"owner": "x", "environment": "prod",
                                  "costcenter": "CC-1"})
    assert fire("CAF-GOV-001", ok) is None


def test_required_tags_skips_untaggable_kinds():
    """An NSG rule has no tags block; flagging it would be pure noise."""
    res = resource("azurerm_network_security_rule", name="allow-x")
    assert fire("CAF-GOV-001", res) is None


def test_approved_region():
    assert fire("CAF-LZ-001", resource(location="brazilsouth")) is not None
    assert fire("CAF-LZ-001", resource(location="centralindia")) is None
    # Region unknown at plan time must not be reported as a violation.
    assert fire("CAF-LZ-001", resource(name="a")) is None


def test_public_network_boundary():
    assert fire("CAF-LZ-002", resource(public_network_access_enabled=True)) is not None
    assert fire("CAF-LZ-002", resource(public_network_access_enabled=False)) is None


def test_wildcard_role_assignment_is_critical():
    res = resource("azurerm_role_assignment",
                   role_definition_name="Owner",
                   scope="/subscriptions/abc")
    finding = fire("CAF-IAM-001", res)
    assert finding is not None
    assert finding.severity is Severity.CRITICAL
    scoped = resource("azurerm_role_assignment",
                      role_definition_name="Storage Blob Data Reader",
                      scope="/subscriptions/abc/resourceGroups/rg")
    assert fire("CAF-IAM-001", scoped) is None


def test_gcp_owner_role_detected():
    res = resource("google_project_iam_member", role="roles/owner")
    assert fire("CAF-IAM-001", res) is not None


# --- WAF security ------------------------------------------------------

def test_https_only():
    assert fire("WAF-SEC-001", resource(https_traffic_only_enabled=False)) is not None
    assert fire("WAF-SEC-001", resource(https_traffic_only_enabled=True)) is None


@pytest.mark.parametrize("value,violates", [
    ("TLS1_0", True), ("TLS1_1", True), ("TLS1_2", False), ("TLS1_3", False),
    ("1.0", True), ("1.2", False),
])
def test_minimum_tls_across_notations(value, violates):
    res = resource(min_tls_version=value)
    assert (fire("WAF-SEC-002", res) is not None) is violates


def test_public_blob_access_azure_and_aws():
    assert fire("WAF-SEC-003",
                resource(allow_nested_items_to_be_public=True)) is not None
    assert fire("WAF-SEC-003",
                resource("aws_s3_bucket", acl="public-read")) is not None
    assert fire("WAF-SEC-003",
                resource("aws_s3_bucket", acl="private")) is None


def test_open_ingress_azure_nsg():
    res = resource("azurerm_network_security_rule", direction="Inbound",
                   access="Allow", destination_port_range="22",
                   source_address_prefix="*")
    assert fire("WAF-SEC-004", res) is not None


def test_open_ingress_ignores_deny_and_outbound():
    deny = resource("azurerm_network_security_rule", direction="Inbound",
                    access="Deny", destination_port_range="22",
                    source_address_prefix="*")
    assert fire("WAF-SEC-004", deny) is None
    out = resource("azurerm_network_security_rule", direction="Outbound",
                   access="Allow", destination_port_range="22",
                   source_address_prefix="*")
    assert fire("WAF-SEC-004", out) is None


def test_open_ingress_ignores_restricted_source():
    res = resource("azurerm_network_security_rule", direction="Inbound",
                   access="Allow", destination_port_range="22",
                   source_address_prefix="10.0.0.0/16")
    assert fire("WAF-SEC-004", res) is None


def test_open_ingress_aws_nested_blocks():
    res = resource("aws_security_group", ingress=[
        {"from_port": 3389, "to_port": 3389, "cidr_blocks": ["0.0.0.0/0"]}
    ])
    assert fire("WAF-SEC-004", res) is not None


def test_open_ingress_gcp_source_ranges():
    res = resource("google_compute_firewall", direction="INGRESS",
                   source_ranges=["0.0.0.0/0"],
                   allow=[{"protocol": "tcp", "ports": ["22"]}])
    assert fire("WAF-SEC-004", res) is not None


def test_hardcoded_secret():
    res = resource("azurerm_mssql_server",
                   administrator_login_password="P@ssw0rd")
    finding = fire("WAF-SEC-006", res)
    assert finding is not None
    assert finding.severity is Severity.CRITICAL


def test_secret_reference_is_not_a_hardcoded_secret():
    res = resource("azurerm_mssql_server", administrator_login_password="${var.pw}")
    assert fire("WAF-SEC-006", res) is None


# --- WAF reliability ---------------------------------------------------

def test_lrs_flagged_for_prod_but_not_dev():
    prod = resource(account_replication_type="LRS", tags={"environment": "prod"})
    assert fire("WAF-REL-001", prod) is not None
    dev = resource(account_replication_type="LRS", tags={"environment": "dev"})
    assert fire("WAF-REL-001", dev) is None
    zrs = resource(account_replication_type="ZRS", tags={"environment": "prod"})
    assert fire("WAF-REL-001", zrs) is None


def test_backup_retention_threshold():
    assert fire("WAF-REL-002",
                resource("azurerm_mssql_server", backup_retention_days=1)) is not None
    assert fire("WAF-REL-002",
                resource("azurerm_mssql_server", backup_retention_days=7)) is None


def test_purge_protection():
    assert fire("WAF-REL-003",
                resource("azurerm_key_vault",
                         purge_protection_enabled=False)) is not None
    assert fire("WAF-REL-003",
                resource("azurerm_key_vault", purge_protection_enabled=True,
                         soft_delete_retention_days=7)) is None


# --- WAF cost ----------------------------------------------------------

def test_oversized_sku_only_in_nonprod():
    dev = resource("azurerm_linux_virtual_machine", size="Standard_D8s_v3",
                   tags={"environment": "dev"})
    assert fire("WAF-COST-001", dev) is not None
    prod = resource("azurerm_linux_virtual_machine", size="Standard_D8s_v3",
                    tags={"environment": "prod"})
    assert fire("WAF-COST-001", prod) is None
    small = resource("azurerm_linux_virtual_machine", size="Standard_B1s",
                     tags={"environment": "dev"})
    assert fire("WAF-COST-001", small) is None


# --- catalogue integrity -----------------------------------------------

def test_every_rule_is_well_formed():
    """Documentation is part of the deliverable, so enforce it."""
    for rule in all_rules():
        assert rule.id, "rule missing id"
        assert rule.title, "{} missing title".format(rule.id)
        assert rule.rationale, "{} missing framework rationale".format(rule.id)
        assert rule.remediation, "{} missing remediation".format(rule.id)


def test_rule_ids_are_unique():
    ids = [r.id for r in all_rules()]
    assert len(ids) == len(set(ids))


def test_both_frameworks_are_covered():
    frameworks = {r.pillar.framework for r in all_rules()}
    assert frameworks == {"CAF", "WAF"}
