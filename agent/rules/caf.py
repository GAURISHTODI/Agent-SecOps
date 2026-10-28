"""Cloud Adoption Framework rules -- portfolio-level governance.

CAF asks "is this change being adopted the right way?": is it tagged and
owned, does it land in an approved region/subscription, is its cost
governed, and is the identity granted to it least-privilege?
"""
from __future__ import annotations

import json
import re
from typing import List, Optional

from ..models import Kind, Pillar, Provider, Resource, Severity
from .base import Rule, missing_tags, register, truthy

# Resource kinds that Terraform models as pure bindings/associations and
# that legitimately carry no tags of their own.
_UNTAGGABLE = (Kind.IAM_BINDING, Kind.NETWORK_FIREWALL, Kind.OTHER)


@register
class RequiredTags(Rule):
    id = "CAF-GOV-001"
    title = "Resource is missing mandatory governance tags"
    pillar = Pillar.CAF_GOVERNANCE
    severity = Severity.MEDIUM
    rationale = (
        "CAF governance requires every deployed resource to carry ownership "
        "and cost-attribution metadata so that spend, incidents and lifecycle "
        "decisions can be traced back to a team."
    )
    remediation = "Add the mandatory tags to the resource's tags/labels block."
    terraform_fix = (
        'tags = {\n'
        '  owner       = "platform-team@example.com"\n'
        '  environment = "prod"\n'
        '  costcenter  = "CC-1042"\n'
        '}'
    )
    params = {"required": ["owner", "environment", "costcenter"]}

    def applies_to(self, resource: Resource) -> bool:
        if resource.kind in _UNTAGGABLE:
            return False
        return super().applies_to(resource)

    def check(self, resource: Resource) -> Optional[str]:
        required = list(self.param("required", []))
        missing = missing_tags(resource, required)
        if not missing:
            return None
        found = sorted(resource.tags) or ["<none>"]
        return (
            "Missing mandatory tag(s): {}. Tags present: {}.".format(
                ", ".join(missing), ", ".join(found)
            )
        )


@register
class NamingConvention(Rule):
    id = "CAF-GOV-002"
    title = "Resource name does not follow the organisation naming standard"
    pillar = Pillar.CAF_GOVERNANCE
    severity = Severity.LOW
    rationale = (
        "CAF prescribes a consistent naming standard "
        "(<workload>-<env>-<region>-<type>) so resources are identifiable "
        "and automatable across subscriptions."
    )
    remediation = (
        "Rename the resource to match <workload>-<env>-<region>-<abbrev>, "
        "e.g. shop-prod-cin-st."
    )
    params = {
        "pattern": r"^[a-z0-9]+-(dev|test|stage|prod)-[a-z0-9]+(-[a-z0-9]+)*$",
        # Azure storage account names forbid hyphens, and rules/bindings are
        # child objects whose names describe intent ("allow-https-from-edge")
        # rather than identifying a governed resource.
        "exempt_kinds": ["object_storage", "network_firewall", "iam_binding", "other"],
    }

    def check(self, resource: Resource) -> Optional[str]:
        if resource.kind.value in list(self.param("exempt_kinds", [])):
            return None
        name = resource.after.get("name")
        if not isinstance(name, str) or not name:
            return None  # name computed at apply time; nothing to judge
        pattern = str(self.param("pattern"))
        if re.match(pattern, name):
            return None
        return (
            'Name "{}" does not match the required convention {}.'.format(name, pattern)
        )


def _same_region(location: str, approved: str) -> bool:
    """Exact region match, also accepting a zone inside that region.

    A plain prefix test would accept "eastus2" for "eastus", which are
    different regions. Zones are spelled "us-east-1a" on AWS and
    "us-east1-b" on GCP, so a single trailing zone letter is allowed.
    """
    if location == approved:
        return True
    return bool(re.fullmatch(re.escape(approved) + r"-?[a-z]", location))


@register
class ApprovedRegion(Rule):
    id = "CAF-LZ-001"
    title = "Resource deploys outside an approved landing-zone region"
    pillar = Pillar.CAF_LANDING_ZONE
    severity = Severity.HIGH
    rationale = (
        "CAF landing zones pin workloads to approved regions for data "
        "residency, latency and sovereignty commitments; deploying elsewhere "
        "silently breaks those commitments."
    )
    remediation = "Move the resource into one of the approved regions."
    # Each cloud names its regions differently ("eastus" vs "us-east-1" vs
    # "us-east1"), so an Azure-only list would flag every compliant AWS or GCP
    # deployment. `approved` is the Azure list (kept for backward
    # compatibility with existing policy files); the others are per cloud.
    params = {
        "approved": ["centralindia", "southindia", "eastus", "westeurope"],
        "approved_aws": ["ap-south-1", "ap-south-2", "us-east-1", "eu-west-1"],
        "approved_gcp": ["asia-south1", "asia-south2", "us-east1", "europe-west4"],
    }

    def _approved_for(self, resource: Resource) -> List[str]:
        key = {
            Provider.AWS: "approved_aws",
            Provider.GCP: "approved_gcp",
        }.get(resource.provider, "approved")
        return [str(a).lower().replace(" ", "") for a in self.param(key, [])]

    def check(self, resource: Resource) -> Optional[str]:
        location = (
            resource.after.get("location")
            or resource.after.get("region")
            or resource.after.get("availability_zone")
        )
        if not isinstance(location, str) or not location:
            return None
        approved = self._approved_for(resource)
        norm = location.lower().replace(" ", "")
        if any(_same_region(norm, a) for a in approved):
            return None
        return (
            'Deploys to region "{}", which is not in the approved landing-zone '
            "region list ({}).".format(location, ", ".join(approved))
        )


@register
class PublicNetworkBoundary(Rule):
    id = "CAF-LZ-002"
    title = "Resource crosses the landing-zone network boundary"
    pillar = Pillar.CAF_LANDING_ZONE
    severity = Severity.HIGH
    kinds = (Kind.OBJECT_STORAGE, Kind.MANAGED_DATABASE, Kind.SECRET_STORE)
    rationale = (
        "CAF landing zones expect data-tier services to be reachable only "
        "from inside the platform's virtual network, via private endpoints "
        "rather than the public service endpoint."
    )
    remediation = (
        "Set public_network_access_enabled = false and expose the service "
        "through a private endpoint."
    )
    terraform_fix = "public_network_access_enabled = false"

    def check(self, resource: Resource) -> Optional[str]:
        flag = resource.after.get("public_network_access_enabled")
        if flag is None:
            flag = resource.after.get("public_network_access")
        if flag is None:
            return None
        if truthy(flag) or str(flag).lower() == "enabled":
            return (
                "Public network access is enabled, so the service is reachable "
                "from outside the landing-zone virtual network."
            )
        return None


@register
class BudgetGovernance(Rule):
    id = "CAF-COST-001"
    title = "Expensive SKU deployed without cost-centre attribution"
    pillar = Pillar.CAF_COST_MANAGEMENT
    severity = Severity.MEDIUM
    kinds = (Kind.COMPUTE_INSTANCE, Kind.MANAGED_DATABASE, Kind.CONTAINER_PLATFORM,
             Kind.APP_HOSTING)
    rationale = (
        "CAF cost management requires that any resource capable of generating "
        "material spend is attributable to a budget owner before it is "
        "provisioned, so budget alerts have somewhere to fire."
    )
    remediation = 'Add a costcenter tag and register the workload against a budget.'
    params = {"tag": "costcenter"}

    def check(self, resource: Resource) -> Optional[str]:
        tag = str(self.param("tag", "costcenter"))
        if tag.lower() in {k.lower() for k in resource.tags}:
            return None
        sku = (
            resource.after.get("sku_name")
            or resource.after.get("size")
            or resource.after.get("instance_type")
            or resource.after.get("instance_class")   # AWS RDS
            or resource.after.get("machine_type")
            or resource.after.get("tier")
            or resource.get("settings.tier")          # GCP Cloud SQL
            or "unspecified"
        )
        return (
            'Billable resource (SKU "{}") carries no "{}" tag, so its spend '
            "cannot be attributed to a budget.".format(sku, tag)
        )


@register
class WildcardRoleAssignment(Rule):
    id = "CAF-IAM-001"
    title = "Over-privileged or wildcard identity grant"
    pillar = Pillar.CAF_IDENTITY
    severity = Severity.CRITICAL
    kinds = (Kind.IAM_BINDING,)
    rationale = (
        "CAF identity guidance mandates least privilege: Owner/Contributor at "
        "subscription scope, or an Action/Resource wildcard, hands a workload "
        "far more authority than it needs and turns any compromise into a "
        "tenant-wide incident."
    )
    remediation = (
        "Replace the broad role with a narrowly-scoped built-in or custom role "
        "targeting only the required resource group and actions."
    )
    terraform_fix = (
        'role_definition_name = "Storage Blob Data Reader"\n'
        "scope                = azurerm_storage_account.data.id"
    )
    params = {"forbidden_roles": ["Owner", "Contributor", "User Access Administrator"]}

    @staticmethod
    def _allows_all_actions(raw: object) -> bool:
        """True if an IAM policy document has an Allow statement with Action "*".

        The document is parsed rather than substring-matched: a statement that
        allows specific actions on Resource "*" (very common and legitimate,
        e.g. s3:GetObject) is not a wildcard-action grant.
        """
        try:
            doc = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            return False
        if not isinstance(doc, dict):
            return False
        statements = doc.get("Statement", [])
        if isinstance(statements, dict):
            statements = [statements]
        for stmt in statements if isinstance(statements, list) else []:
            if not isinstance(stmt, dict) or stmt.get("Effect") != "Allow":
                continue
            actions = stmt.get("Action", [])
            actions = [actions] if isinstance(actions, str) else list(actions or [])
            if "*" in actions:
                return True
        return False

    def check(self, resource: Resource) -> Optional[str]:
        problems: List[str] = []

        role = resource.after.get("role_definition_name")
        forbidden = [str(r).lower() for r in self.param("forbidden_roles", [])]
        if isinstance(role, str) and role.lower() in forbidden:
            scope = str(resource.after.get("scope", ""))
            broad = "/resourceGroups/" not in scope
            # Contributor scoped to one resource group is the normal way to
            # let a pipeline deploy into that group (this project's own CI
            # identity does exactly that); it is only a finding at
            # subscription / management-group scope. Owner and User Access
            # Administrator can grant access to others, so they are flagged
            # at any scope.
            if broad or role.lower() != "contributor":
                problems.append(
                    'Grants the highly-privileged role "{}"{}.'.format(
                        role,
                        " at subscription/management-group scope" if broad else "",
                    )
                )

        # AWS / GCP style policy documents
        policy = resource.after.get("policy") or resource.after.get("policy_data")
        if self._allows_all_actions(policy):
            problems.append("Policy document allows wildcard (*) actions.")
        member = str(resource.after.get("role", ""))
        if member.endswith("/owner") or member == "roles/owner":
            problems.append("Binds the GCP roles/owner primitive role.")

        return " ".join(problems) if problems else None


@register
class PublicIpWithoutJustification(Rule):
    id = "CAF-LZ-003"
    title = "Public IP allocated without a documented exposure justification"
    pillar = Pillar.CAF_LANDING_ZONE
    severity = Severity.MEDIUM
    kinds = (Kind.NETWORK_PUBLIC_IP,)
    rationale = (
        "In a CAF landing zone, internet ingress is expected to arrive through "
        "shared platform edge services; a workload-owned public IP is an "
        "exception that must be justified in metadata."
    )
    remediation = (
        'Route traffic through the platform gateway, or tag the resource with '
        'exposure="public-approved" plus the approving ticket.'
    )
    params = {"justification_tag": "exposure"}

    def check(self, resource: Resource) -> Optional[str]:
        tag = str(self.param("justification_tag", "exposure"))
        if tag.lower() in {k.lower() for k in resource.tags}:
            return None
        return (
            "Allocates a public IP address but carries no \"{}\" tag "
            "justifying internet exposure.".format(tag)
        )
