"""Terraform plan JSON -> normalized `Resource` objects.

Input is the output of:
    terraform plan -out=tf.plan && terraform show -json tf.plan > plan.json

The parser only understands Terraform's documented plan schema (format
version 0.1/1.x), so it never needs Terraform installed to run -- which is
what lets the gate execute on a free GitHub-hosted runner in seconds.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

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
    # Likewise a storage container has no tags, region or logs of its own;
    # the engine folds its access level onto the parent storage account.
    "azurerm_storage_container": Kind.OTHER,
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
    # AWS provider v4+ splits a bucket's ACL, versioning, encryption and so on
    # into separate resources. They are settings of the bucket, not buckets,
    # so the engine folds them onto their parent instead.
    if t.startswith("aws_s3_bucket_"):
        return Kind.OTHER
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


def _provider_regions(data: Dict[str, Any]) -> Dict[str, str]:
    """Map provider name (aws, google, ...) to its configured default region.

    In a real `terraform show -json` plan the region of an AWS or GCP
    resource usually lives on the provider block, not on the resource, so a
    rule that only looks at the resource would never see it.
    """
    configs = (data.get("configuration") or {}).get("provider_config") or {}
    regions: Dict[str, str] = {}
    for cfg in configs.values():
        name = cfg.get("name")
        exprs = cfg.get("expressions") or {}
        for key in ("region", "location"):
            value = (exprs.get(key) or {}).get("constant_value")
            if name and isinstance(value, str) and value:
                regions.setdefault(name, value)
    return regions


# Providers whose resources inherit the provider-level region, and the
# resource-type prefixes that are global despite that (IAM has no region),
# or that are settings of a parent resource rather than placed resources.
_REGIONAL_PROVIDERS = {"aws": "aws_", "google": "google_"}
_GLOBAL_PREFIXES = (
    "aws_iam_", "aws_route53_", "aws_cloudfront_", "aws_s3_bucket_",
    "google_project_iam", "google_service_account", "google_compute_firewall",
    "google_compute_network", "google_compute_global_",
)


def _inherit_region(rtype: str, after: Dict[str, Any], regions: Dict[str, str]) -> None:
    if after.get("region") or after.get("location"):
        return
    if rtype.startswith(_GLOBAL_PREFIXES):
        return
    for provider, prefix in _REGIONAL_PROVIDERS.items():
        if rtype.startswith(prefix) and provider in regions:
            after["region"] = regions[provider]
            return


def _collect_references(node: Any, out: List[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "references" and isinstance(value, list):
                out.extend(str(v) for v in value)
            else:
                _collect_references(value, out)
    elif isinstance(node, list):
        for value in node:
            _collect_references(value, out)


_INDEX = re.compile(r"\[[^\]]*\]$")


def _resolve(ref: str, prefix: str, inputs: Dict[str, List[str]]) -> List[str]:
    """Turn a reference made inside a module into plan-wide references.

    ``var.sg_id`` inside ``module.web`` means whatever the parent passed in as
    ``sg_id``; anything else is local to the module and gets its prefix.
    """
    if ref.startswith("var."):
        return inputs.get(ref.split(".")[1], [])
    return [prefix + ref]


ModuleInputs = Dict[str, List[str]]


def _config_resources(
    module: Dict[str, Any], prefix: str = "", inputs: Optional[ModuleInputs] = None
) -> List[Tuple[str, ModuleInputs, Dict[str, Any]]]:
    """(module prefix, module inputs, resource config) for every module.

    Module inputs map each variable of a child module to the plan-wide
    references the parent passed into it, so a resource handed to a module
    stays connected to what the module builds from it.
    """
    inputs = inputs or {}
    found = [(prefix, inputs, res) for res in module.get("resources", []) or []]
    for name, call in (module.get("module_calls") or {}).items():
        child_inputs: ModuleInputs = {}
        for var, expr in ((call or {}).get("expressions") or {}).items():
            refs: List[str] = []
            _collect_references(expr, refs)
            child_inputs[var] = [r for ref in refs for r in _resolve(ref, prefix, inputs)]
        child = (call or {}).get("module") or {}
        found.extend(
            _config_resources(child, "{}module.{}.".format(prefix, name), child_inputs)
        )
    return found


def _configuration_facts(
    data: Dict[str, Any], known: Set[str]
) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    """Dependency edges and referenced attributes from the `configuration` block.

    Edges map a resource to the resources it references; a reference such as
    ``azurerm_subnet.app.id`` is reduced to ``azurerm_subnet.app``, and
    anything that is not a resource in this plan (variables, data sources,
    locals) is ignored. Configuration addresses carry no ``count`` /
    ``for_each`` index, so each one is expanded to every planned instance.
    """
    module = (data.get("configuration") or {}).get("root_module") or {}
    instances: Dict[str, List[str]] = {}
    for address in known:
        instances.setdefault(_INDEX.sub("", address), []).append(address)

    edges: Dict[str, List[str]] = {}
    referenced: Dict[str, List[str]] = {}
    for prefix, inputs, res in _config_resources(module):
        base = prefix + str(res.get("address", ""))
        owners = instances.get(base)
        if not owners:
            continue
        expressions = res.get("expressions", {}) or {}
        refs: List[str] = []
        _collect_references(expressions, refs)
        refs.extend(str(d) for d in res.get("depends_on", []) or [])
        targets: List[str] = []
        for ref in (r for raw in refs for r in _resolve(raw, prefix, inputs)):
            parts = ref.split(".")
            for end in range(2, len(parts) + 1):
                cand = _INDEX.sub("", ".".join(parts[:end]))
                if cand in instances and cand != base:
                    for inst in instances[cand]:
                        if inst not in targets:
                            targets.append(inst)
                    break
        attrs = sorted(
            key for key, expr in expressions.items()
            if isinstance(expr, dict) and expr.get("references")
        )
        for owner in owners:
            if targets:
                edges[owner] = list(targets)
            if attrs:
                referenced[owner] = attrs
    return edges, referenced


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
    regions = _provider_regions(data)
    for rc in changes:
        rtype = rc.get("type", "")
        change = rc.get("change", {}) or {}
        action = _action_of(change.get("actions", []))
        if action in (Action.NOOP, Action.READ):
            continue  # nothing is being provisioned; nothing to gate
        provider = detect_provider(rtype)
        after = dict(change.get("after") or {})
        _inherit_region(rtype, after, regions)
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
                after=after,
                before=change.get("before") or {},
                module=_module_of(rc.get("address", "")),
            )
        )

    edges, referenced = _configuration_facts(data, {r.address for r in resources})
    for resource in resources:
        resource.referenced_attrs = referenced.get(resource.address, [])

    return PlanSummary(
        resources=resources,
        terraform_version=data.get("terraform_version", "unknown"),
        format_version=data.get("format_version", "unknown"),
        providers=providers,
        edges=edges,
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
