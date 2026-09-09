"""Terraform plan JSON -> normalized `Resource` objects.

Input is the output of:
    terraform plan -out=tf.plan && terraform show -json tf.plan > plan.json

The parser only understands Terraform's documented plan schema (format
version 0.1/1.x), so it never needs Terraform installed to run -- which is
what lets the gate execute on a free GitHub-hosted runner in seconds.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Union

from .models import Action, Kind, PlanSummary, Provider, Resource

# --- provider detection ------------------------------------------------
_PROVIDER_PREFIX = {
    "azurerm_": Provider.AZURE,
    "azuread_": Provider.AZURE,
    "azapi_": Provider.AZURE,
    "aws_": Provider.AWS,
    "google_": Provider.GCP,
    "google-beta_": Provider.GCP,
}

# --- canonical kind mapping -------------------------------------------
# This table is the whole multi-cloud story: one rule keyed on a Kind
# automatically covers the Azure, AWS and GCP resource types listed here.
_KIND_MAP: Dict[str, Kind] = {
    # object storage
    "azurerm_storage_account": Kind.OBJECT_STORAGE,
    "azurerm_storage_container": Kind.OBJECT_STORAGE,
    "aws_s3_bucket": Kind.OBJECT_STORAGE,
    "google_storage_bucket": Kind.OBJECT_STORAGE,
    # compute
    "azurerm_linux_virtual_machine": Kind.COMPUTE_INSTANCE,
    "azurerm_windows_virtual_machine": Kind.COMPUTE_INSTANCE,
    "azurerm_virtual_machine": Kind.COMPUTE_INSTANCE,
    "aws_instance": Kind.COMPUTE_INSTANCE,
    "google_compute_instance": Kind.COMPUTE_INSTANCE,
    # databases
    "azurerm_mssql_server": Kind.MANAGED_DATABASE,
    "azurerm_mssql_database": Kind.MANAGED_DATABASE,
    "azurerm_postgresql_flexible_server": Kind.MANAGED_DATABASE,
    "azurerm_cosmosdb_account": Kind.MANAGED_DATABASE,
    "aws_db_instance": Kind.MANAGED_DATABASE,
    "aws_rds_cluster": Kind.MANAGED_DATABASE,
    "google_sql_database_instance": Kind.MANAGED_DATABASE,
    # firewalls / network ACLs
    # Note: a *_firewall_rule belongs here, not with its parent database --
    # it is an access-control object with no tags, SKU or logs of its own.
    "azurerm_network_security_group": Kind.NETWORK_FIREWALL,
    "azurerm_network_security_rule": Kind.NETWORK_FIREWALL,
    "azurerm_mssql_firewall_rule": Kind.NETWORK_FIREWALL,
    "azurerm_sql_firewall_rule": Kind.NETWORK_FIREWALL,
    "azurerm_postgresql_flexible_server_firewall_rule": Kind.NETWORK_FIREWALL,
    "azurerm_cosmosdb_account_firewall_rule": Kind.NETWORK_FIREWALL,
    "aws_security_group": Kind.NETWORK_FIREWALL,
    "aws_security_group_rule": Kind.NETWORK_FIREWALL,
    "google_compute_firewall": Kind.NETWORK_FIREWALL,
    # public addressing
    "azurerm_public_ip": Kind.NETWORK_PUBLIC_IP,
    "aws_eip": Kind.NETWORK_PUBLIC_IP,
    "google_compute_address": Kind.NETWORK_PUBLIC_IP,
    # secrets
    "azurerm_key_vault": Kind.SECRET_STORE,
    "azurerm_key_vault_secret": Kind.SECRET_STORE,
    "aws_secretsmanager_secret": Kind.SECRET_STORE,
    "aws_kms_key": Kind.SECRET_STORE,
    "google_secret_manager_secret": Kind.SECRET_STORE,
    # identity
    "azurerm_role_assignment": Kind.IAM_BINDING,
    "aws_iam_role_policy": Kind.IAM_BINDING,
    "aws_iam_policy": Kind.IAM_BINDING,
    "aws_iam_role": Kind.IAM_BINDING,
    "google_project_iam_member": Kind.IAM_BINDING,
    "google_project_iam_binding": Kind.IAM_BINDING,
    # containers
    "azurerm_kubernetes_cluster": Kind.CONTAINER_PLATFORM,
    "aws_eks_cluster": Kind.CONTAINER_PLATFORM,
    "google_container_cluster": Kind.CONTAINER_PLATFORM,
    # grouping / scope
    "azurerm_resource_group": Kind.RESOURCE_GROUP,
    "google_project": Kind.RESOURCE_GROUP,
    # observability
    "azurerm_log_analytics_workspace": Kind.LOG_WORKSPACE,
    "aws_cloudwatch_log_group": Kind.LOG_WORKSPACE,
    "google_logging_project_sink": Kind.LOG_WORKSPACE,
    # A diagnostic *setting* is an attachment, not an observability store of
    # its own: it has no tags, name convention or SKU to govern. It still
    # matters to the engine, which reads it to satisfy WAF-OPS-001.
    "azurerm_monitor_diagnostic_setting": Kind.OTHER,
    # app hosting
    "azurerm_linux_web_app": Kind.APP_HOSTING,
    "azurerm_windows_web_app": Kind.APP_HOSTING,
    "azurerm_service_plan": Kind.APP_HOSTING,
    "azurerm_container_group": Kind.APP_HOSTING,
    "aws_lambda_function": Kind.APP_HOSTING,
    "google_cloud_run_service": Kind.APP_HOSTING,
}


class PlanParseError(ValueError):
    """Raised when the file is not a recognisable Terraform plan JSON."""


def detect_provider(resource_type: str) -> Provider:
    for prefix, provider in _PROVIDER_PREFIX.items():
        if resource_type.startswith(prefix):
            return provider
    return Provider.UNKNOWN


def classify(resource_type: str) -> Kind:
    """Map a provider resource type to its canonical kind.

    Falls back to substring heuristics so an unseen type still lands in a
    sensible bucket instead of being silently ignored by every rule.
    """
    if resource_type in _KIND_MAP:
        return _KIND_MAP[resource_type]
    t = resource_type.lower()
    # Firewall/ACL objects are matched first: "mssql_firewall_rule" contains
    # "sql", so a database check ahead of this would misclassify it.
    if "security_group" in t or "firewall" in t or "security_rule" in t:
        return Kind.NETWORK_FIREWALL
    if "storage" in t or "bucket" in t or "blob" in t:
        return Kind.OBJECT_STORAGE
    if "virtual_machine" in t or "instance" in t:
        return Kind.COMPUTE_INSTANCE
    if "sql" in t or "database" in t or "cosmos" in t or "rds" in t:
        return Kind.MANAGED_DATABASE
    if "key_vault" in t or "secret" in t or "kms" in t:
        return Kind.SECRET_STORE
    if "iam" in t or "role_assignment" in t or "policy" in t:
        return Kind.IAM_BINDING
    if "kubernetes" in t or "eks" in t or "container_cluster" in t:
        return Kind.CONTAINER_PLATFORM
    if "log" in t or "monitor" in t or "diagnostic" in t:
        return Kind.LOG_WORKSPACE
    return Kind.OTHER


def _action_of(actions: List[str]) -> Action:
    """Collapse Terraform's action list into a single verb.

    ["delete", "create"] is Terraform's encoding of a replacement, which
    matters here: a replace re-creates the resource, so every create-time
    rule must still run against it.
    """
    s = set(actions or [])
    if "delete" in s and "create" in s:
        return Action.REPLACE
    if "create" in s:
        return Action.CREATE
    if "update" in s:
        return Action.UPDATE
    if "delete" in s:
        return Action.DELETE
    if "read" in s:
        return Action.READ
    return Action.NOOP


def _module_of(address: str) -> str:
    if address.startswith("module."):
        return ".".join(address.split(".")[:2])
    return "root"


def parse_plan(data: Dict[str, Any]) -> PlanSummary:
    """Turn a decoded plan JSON document into a `PlanSummary`."""
    if not isinstance(data, dict):
        raise PlanParseError("Plan JSON root must be an object.")
    changes = data.get("resource_changes")
    if changes is None:
        raise PlanParseError(
            "No 'resource_changes' key found. Generate the plan with: "
            "terraform plan -out=tf.plan && terraform show -json tf.plan > plan.json"
        )

    resources: List[Resource] = []
    providers: List[Provider] = []
    for rc in changes:
        rtype = rc.get("type", "")
        change = rc.get("change", {}) or {}
        action = _action_of(change.get("actions", []))
        if action in (Action.NOOP, Action.READ):
            continue  # nothing is being provisioned; nothing to gate
        provider = detect_provider(rtype)
        if provider not in providers and provider != Provider.UNKNOWN:
            providers.append(provider)
        resources.append(
            Resource(
                address=rc.get("address", rtype),
                type=rtype,
                name=rc.get("name", ""),
                provider=provider,
                kind=classify(rtype),
                action=action,
                after=change.get("after") or {},
                before=change.get("before") or {},
                module=_module_of(rc.get("address", "")),
            )
        )

    return PlanSummary(
        resources=resources,
        terraform_version=data.get("terraform_version", "unknown"),
        format_version=data.get("format_version", "unknown"),
        providers=providers,
    )


def load_plan(path: Union[str, Path]) -> PlanSummary:
    p = Path(path)
    if not p.exists():
        raise PlanParseError("Plan file not found: {}".format(p))
    try:
        # utf-8-sig tolerates a leading BOM and is a no-op when there isn't
        # one. PowerShell's `Out-File -Encoding utf8` (the natural way to
        # redirect `terraform show -json` on Windows) always writes a BOM,
        # so strict utf-8 here would reject every plan produced that way.
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise PlanParseError("{} is not valid JSON: {}".format(p, exc)) from exc
    return parse_plan(data)
