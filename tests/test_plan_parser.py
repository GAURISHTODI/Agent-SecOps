"""Parser tests: the gate is only as trustworthy as its plan reading."""
from __future__ import annotations

import pytest

from agent.models import Action, Kind, Provider
from agent.plan_parser import PlanParseError, classify, detect_provider, parse_plan


def _plan(*changes):
    return {"format_version": "1.2", "terraform_version": "1.9.5",
            "resource_changes": list(changes)}


def _change(address, rtype, actions, after):
    return {
        "address": address,
        "type": rtype,
        "name": address.split(".")[-1],
        "change": {"actions": actions, "before": None, "after": after},
    }


def test_detects_each_provider():
    assert detect_provider("azurerm_storage_account") is Provider.AZURE
    assert detect_provider("aws_s3_bucket") is Provider.AWS
    assert detect_provider("google_storage_bucket") is Provider.GCP
    assert detect_provider("random_password") is Provider.UNKNOWN


def test_same_kind_across_three_clouds():
    """The multi-cloud claim in one assertion."""
    for rtype in ("azurerm_storage_account", "aws_s3_bucket", "google_storage_bucket"):
        assert classify(rtype) is Kind.OBJECT_STORAGE


def test_firewall_rule_is_not_a_database():
    """Regression: 'mssql_firewall_rule' contains 'sql'."""
    assert classify("azurerm_mssql_firewall_rule") is Kind.NETWORK_FIREWALL
    assert classify("azurerm_postgresql_flexible_server_firewall_rule") is (
        Kind.NETWORK_FIREWALL
    )


def test_unknown_type_falls_back_to_heuristic_not_silence():
    assert classify("azurerm_some_new_storage_thing") is Kind.OBJECT_STORAGE
    assert classify("totally_unrelated_widget") is Kind.OTHER


def test_replace_is_treated_as_create():
    """A replace re-creates the resource, so create-time rules must run."""
    plan = parse_plan(_plan(_change("a.b", "azurerm_storage_account",
                                    ["delete", "create"], {"name": "x"})))
    assert plan.resources[0].action is Action.REPLACE
    assert plan.resources[0].is_mutating


def test_noop_and_read_are_skipped():
    plan = parse_plan(_plan(
        _change("a.b", "azurerm_storage_account", ["no-op"], {}),
        _change("a.c", "azurerm_storage_account", ["read"], {}),
        _change("a.d", "azurerm_storage_account", ["create"], {"name": "x"}),
    ))
    assert [r.address for r in plan.resources] == ["a.d"]


def test_delete_is_parsed_but_not_mutating():
    plan = parse_plan(_plan(_change("a.b", "azurerm_storage_account",
                                    ["delete"], {})))
    assert plan.resources[0].action is Action.DELETE
    assert not plan.resources[0].is_mutating


def test_nested_block_lookup_steps_into_single_element_lists():
    plan = parse_plan(_plan(_change(
        "a.b", "azurerm_storage_account", ["create"],
        {"network_rules": [{"default_action": "Deny"}]},
    )))
    assert plan.resources[0].get("network_rules.default_action") == "Deny"
    assert plan.resources[0].get("network_rules.missing", "fallback") == "fallback"


def test_aws_style_tag_list_is_normalised():
    plan = parse_plan(_plan(_change(
        "a.b", "aws_s3_bucket", ["create"],
        {"tags": [{"key": "owner", "value": "team"}]},
    )))
    assert plan.resources[0].tags == {"owner": "team"}


def test_gcp_labels_count_as_tags():
    plan = parse_plan(_plan(_change(
        "a.b", "google_storage_bucket", ["create"], {"labels": {"owner": "team"}},
    )))
    assert plan.resources[0].tags["owner"] == "team"


def test_missing_resource_changes_raises_actionable_error():
    with pytest.raises(PlanParseError, match="resource_changes"):
        parse_plan({"format_version": "1.2"})


def test_module_address_is_recorded():
    plan = parse_plan(_plan(_change(
        "module.network.azurerm_public_ip.pip", "azurerm_public_ip",
        ["create"], {"name": "x"},
    )))
    assert plan.resources[0].module == "module.network"
