"""Offline reasoner -- zero-cost, deterministic Layer 2.

This is the default in CI. It performs the same *shape* of analysis the
LLM performs -- retrieve the pillar guidance for the resource kind, look
for intent violations no rule covers, emit a confidence-scored advisory --
but with hand-written heuristics instead of a model call.

Two reasons it exists:
  1. Cost. Every pipeline run is free, so the gate can run on every PR.
  2. Evaluation. It is the control arm: the research claim is that the LLM
     reasoner finds violations that neither the rules nor these heuristics
     catch, and you cannot measure that without a deterministic baseline.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from ..models import Finding, Kind, Resource
from .base import Reasoner, kb_context, load_kb, make_finding


class _Probe:
    """One heuristic: a targeted question about framework intent."""

    def __init__(
        self,
        kinds,
        title,
        pillar,
        severity,
        confidence,
        test,
        explanation,
        remediation,
        fix=None,
    ):
        self.kinds = kinds
        self.title = title
        self.pillar = pillar
        self.severity = severity
        self.confidence = confidence
        self.test = test
        self.explanation = explanation
        self.remediation = remediation
        self.fix = fix


def _has(resource: Resource, key: str) -> bool:
    return key in resource.after


def _off(resource: Resource, key: str) -> bool:
    """True when the flag is present and explicitly disabled."""
    val = resource.after.get(key)
    return key in resource.after and val is not True and str(val).lower() != "true"


def _on(resource: Resource, key: str) -> bool:
    val = resource.after.get(key)
    return val is True or str(val).lower() == "true"


# The probe table below is the offline stand-in for framework reasoning.
# Each entry corresponds to a "watch_for" line in the knowledge base.
_PROBES: List[_Probe] = [
    _Probe(
        kinds=(Kind.OBJECT_STORAGE,),
        title="Shared access keys left enabled where identity-based auth would do",
        pillar="WAF:Security",
        severity="medium",
        confidence=0.75,
        test=lambda r: _on(r, "shared_access_key_enabled"),
        explanation=(
            "The account still accepts shared access keys. WAF Security prefers "
            "Entra ID / IAM authentication because account keys are long-lived, "
            "shareable and cannot be attributed to a principal."
        ),
        remediation="Set shared_access_key_enabled = false and grant RBAC data roles.",
        fix="shared_access_key_enabled = false",
    ),
    _Probe(
        kinds=(Kind.OBJECT_STORAGE,),
        title="Irreplaceable data stored without versioning",
        pillar="WAF:Reliability",
        severity="medium",
        confidence=0.65,
        test=lambda r: _off(r, "versioning_enabled")
        or (r.get("blob_properties") and _off_nested(r, "versioning_enabled")),
        explanation=(
            "Blob versioning is disabled, so an overwrite or a ransomware-style "
            "bulk write is unrecoverable. WAF Reliability treats object data as "
            "state that must survive operator error, not just infrastructure "
            "failure."
        ),
        remediation="Enable blob versioning and a soft-delete retention window.",
        fix="blob_properties {\n  versioning_enabled = true\n}",
    ),
    _Probe(
        kinds=(Kind.OBJECT_STORAGE, Kind.MANAGED_DATABASE, Kind.SECRET_STORE),
        title="Data service has no network allow-list (open default action)",
        pillar="CAF:LandingZone",
        severity="high",
        confidence=0.8,
        test=lambda r: str(r.get("network_rules.default_action", "")).lower() == "allow"
        or str(r.after.get("default_action", "")).lower() == "allow",
        explanation=(
            "The service's network rule set defaults to Allow, which means the "
            "firewall accepts every source. CAF landing zones expect data-tier "
            "services to default-deny and admit only known subnets or private "
            "endpoints."
        ),
        remediation='Set network_rules.default_action = "Deny" and list the allowed subnets.',
        fix='network_rules {\n  default_action = "Deny"\n  virtual_network_subnet_ids = [var.app_subnet_id]\n}',
    ),
    _Probe(
        kinds=(Kind.MANAGED_DATABASE, Kind.NETWORK_FIREWALL),
        title="Database firewall rule spans the entire IPv4 range",
        pillar="WAF:Security",
        severity="critical",
        confidence=0.9,
        test=lambda r: str(r.after.get("start_ip_address", "")) == "0.0.0.0"
        and str(r.after.get("end_ip_address", "")) in ("255.255.255.255", "0.0.0.0"),
        explanation=(
            "The firewall rule admits every address on the internet. This is the "
            "'Allow Azure services' anti-pattern that WAF Security explicitly "
            "warns against for production data."
        ),
        remediation="Restrict the rule to the workload subnet or use a private endpoint.",
    ),
    _Probe(
        kinds=(Kind.COMPUTE_INSTANCE,),
        title="Virtual machine allows password authentication",
        pillar="WAF:Security",
        severity="high",
        confidence=0.85,
        test=lambda r: _on(r, "disable_password_authentication") is False
        and _has(r, "disable_password_authentication"),
        explanation=(
            "Password authentication is enabled on a Linux VM. WAF Security "
            "requires key-based or identity-based access because passwords are "
            "brute-forceable and rarely rotated."
        ),
        remediation="Set disable_password_authentication = true and attach an SSH key.",
        fix="disable_password_authentication = true",
    ),
    _Probe(
        kinds=(Kind.COMPUTE_INSTANCE,),
        title="Single instance with no availability construct",
        pillar="WAF:Reliability",
        severity="medium",
        confidence=0.6,
        test=lambda r: not any(
            _has(r, k)
            for k in ("zone", "zones", "availability_set_id", "availability_zone")
        ),
        explanation=(
            "The instance is pinned to no availability zone or set, so a single "
            "rack or zone failure takes the workload down. WAF Reliability asks "
            "for an explicit availability decision, not an accidental one."
        ),
        remediation='Place the VM in a zone (zone = "1") or an availability set / scale set.',
    ),
    _Probe(
        kinds=(Kind.CONTAINER_PLATFORM,),
        title="Kubernetes API server publicly reachable",
        pillar="WAF:Security",
        severity="high",
        confidence=0.8,
        test=lambda r: _off(r, "private_cluster_enabled")
        and not r.after.get("api_server_authorized_ip_ranges"),
        explanation=(
            "The cluster API server is public with no authorised IP range. WAF "
            "Security expects the control plane to be private or restricted to "
            "known operator networks."
        ),
        remediation="Enable private_cluster_enabled, or set api_server_authorized_ip_ranges.",
        fix="private_cluster_enabled = true",
    ),
    _Probe(
        kinds=(Kind.CONTAINER_PLATFORM,),
        title="Cluster node pool spans no availability zones",
        pillar="WAF:Reliability",
        severity="medium",
        confidence=0.7,
        test=lambda r: isinstance(r.get("default_node_pool"), dict)
        and not (r.get("default_node_pool") or {}).get("zones"),
        explanation=(
            "The default node pool declares no zones, so every node can land in "
            "one datacentre. WAF Reliability expects zone spread for any workload "
            "with an availability target."
        ),
        remediation='Set zones = ["1", "2", "3"] on the node pool.',
    ),
    _Probe(
        kinds=(Kind.APP_HOSTING,),
        title="Web app does not enforce HTTPS",
        pillar="WAF:Security",
        severity="high",
        confidence=0.85,
        test=lambda r: _off(r, "https_only"),
        explanation=(
            "https_only is disabled, so the app answers on plain HTTP and any "
            "session cookie or token it issues is interceptable."
        ),
        remediation="Set https_only = true.",
        fix="https_only = true",
    ),
    _Probe(
        kinds=(Kind.SECRET_STORE,),
        title="Key vault uses legacy access policies instead of RBAC",
        pillar="CAF:Identity",
        severity="medium",
        confidence=0.65,
        test=lambda r: _off(r, "enable_rbac_authorization")
        or (_has(r, "access_policy") and not _has(r, "enable_rbac_authorization")),
        explanation=(
            "The vault relies on access policies rather than Azure RBAC. CAF "
            "identity guidance prefers RBAC because access policies are not "
            "visible to standard access reviews and drift silently."
        ),
        remediation="Set enable_rbac_authorization = true and assign data-plane roles.",
        fix="enable_rbac_authorization = true",
    ),
    _Probe(
        kinds=(Kind.LOG_WORKSPACE,),
        title="Log retention below the governance minimum",
        pillar="WAF:OperationalExcellence",
        severity="medium",
        confidence=0.7,
        test=lambda r: _retention_below(r, 30),
        explanation=(
            "Log retention is shorter than 30 days, which is below the window "
            "most incident investigations need. WAF Operational Excellence ties "
            "retention to the time it actually takes to detect an issue."
        ),
        remediation="Raise retention_in_days to at least 30.",
        fix="retention_in_days = 30",
    ),
    _Probe(
        kinds=(Kind.IAM_BINDING,),
        title="Role granted at a scope broader than the workload requires",
        pillar="CAF:Identity",
        severity="high",
        confidence=0.7,
        test=lambda r: _scope_is_broad(r),
        explanation=(
            "The assignment is scoped at subscription or management-group level. "
            "CAF identity guidance requires the narrowest scope that satisfies "
            "the requirement, usually a single resource group or resource."
        ),
        remediation="Re-scope the assignment to the specific resource group or resource.",
    ),
]


def _off_nested(resource: Resource, key: str) -> bool:
    block = resource.get("blob_properties")
    if not isinstance(block, dict):
        return False
    return key in block and not (block.get(key) is True)


def _retention_below(resource: Resource, days: int) -> bool:
    for key in ("retention_in_days", "retention_days"):
        if key in resource.after:
            try:
                return int(resource.after[key]) < days
            except (TypeError, ValueError):
                return False
    return False


def _scope_is_broad(resource: Resource) -> bool:
    scope = str(resource.after.get("scope", ""))
    if not scope:
        return False
    if "/resourceGroups/" in scope or "/providers/Microsoft." in scope.split(
        "/resourceGroups/"
    )[-1]:
        return False
    return scope.startswith("/subscriptions/") or scope.startswith(
        "/providers/Microsoft.Management"
    )


class OfflineReasoner(Reasoner):
    """Heuristic Layer 2. Costs nothing, runs in milliseconds."""

    name = "offline"

    def __init__(self, min_confidence: float = 0.6) -> None:
        self.min_confidence = min_confidence
        self.kb = load_kb()

    def analyse(
        self,
        resources: List[Resource],
        already_found: Dict[str, List[str]],
    ) -> List[Finding]:
        findings: List[Finding] = []
        for resource in resources:
            # Retrieval happens even offline, so the two reasoners are
            # comparable: both only consider pillars indexed to this kind.
            context = kb_context(resource.kind.value, self.kb)
            relevant_pillars = set(context.get("pillars", {}).keys())
            seen = {t.lower() for t in already_found.get(resource.address, [])}

            for probe in _PROBES:
                if resource.kind not in probe.kinds:
                    continue
                if relevant_pillars and probe.pillar not in relevant_pillars:
                    continue
                if probe.title.lower() in seen:
                    continue
                if probe.confidence < self.min_confidence:
                    continue
                try:
                    triggered = bool(probe.test(resource))
                except Exception:
                    # A malformed plan attribute must never crash the gate.
                    continue
                if not triggered:
                    continue
                finding = make_finding(
                    resource_address=resource.address,
                    title=probe.title,
                    pillar_name=probe.pillar,
                    severity_name=probe.severity,
                    explanation=probe.explanation,
                    remediation=probe.remediation,
                    confidence=probe.confidence,
                    source="reasoner",
                    terraform_fix=probe.fix,
                    rule_id="REASON-OFFLINE",
                )
                if finding:
                    findings.append(finding)
        return findings
