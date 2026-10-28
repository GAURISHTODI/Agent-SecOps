"""The gate engine: plan in, verdict out.

Pipeline position:

    terraform plan -> plan.json -> [ENGINE] -> pass / remediate / block
                                       |
                                       +-- Layer 1: deterministic CAF/WAF rules
                                       +-- Layer 2: reasoning over framework intent
                                       +-- Layer 3: policy (thresholds + waivers)
"""
from __future__ import annotations

import copy
import time
from collections import Counter
from typing import Dict, List, Optional

from .config import Policy, load_policy
from .models import Finding, GateResult, PlanSummary, Resource, Verdict
from .plan_parser import load_plan
from .reasoner import build_reasoner
from .reasoner.graph import GraphReasoner
from .rules.base import Rule, all_rules


# Types that attach monitoring to another resource. Matched on the type name
# because Azure, AWS and GCP each spell it differently.
_DIAGNOSTIC_MARKERS = ("diagnostic_setting", "_logging", "flow_log")


def _link_diagnostics(plan: PlanSummary) -> None:
    """Mark resources that a diagnostic setting in this plan already covers.

    Terraform expresses this as a separate resource pointing back via
    `target_resource_id`, so the check is inherently cross-resource --
    a rule looking at one resource in isolation could never see it. The
    engine resolves it before rules run.
    """
    attachments = [
        r for r in plan.resources
        if any(marker in r.type for marker in _DIAGNOSTIC_MARKERS)
    ]
    covered: set = set()
    for resource in attachments:
        target = resource.after.get("target_resource_id")
        if isinstance(target, str) and target:
            covered.add(target)
        # Hand-written fixtures have no dependency graph and unresolved ids,
        # so fall back to the setting sharing the target's local name.
        if resource.name:
            covered.add(resource.name)

    # Real plans carry the dependency graph: a diagnostic setting that
    # references a resource covers exactly that resource. This is exact where
    # the name match above is a heuristic.
    by_addr = {r.address: r for r in plan.resources}
    for resource in attachments:
        for target in plan.edges.get(resource.address, []):
            if target in by_addr and by_addr[target] is not resource:
                by_addr[target].after["_has_diagnostics"] = True

    for resource in plan.resources:
        if resource in attachments:
            continue
        if resource.name and resource.name in covered:
            resource.after["_has_diagnostics"] = True
        rid = resource.after.get("id")
        if isinstance(rid, str) and rid in covered:
            resource.after["_has_diagnostics"] = True


def _versioning_status(after: Dict[str, object]) -> Optional[bool]:
    block = after.get("versioning_configuration")
    if isinstance(block, list) and block and isinstance(block[0], dict):
        return str(block[0].get("status", "")).lower() == "enabled"
    return None


def _sse_key(after: Dict[str, object]) -> Optional[str]:
    for rule in after.get("rule") or []:
        for default in (rule or {}).get("apply_server_side_encryption_by_default") or []:
            key = (default or {}).get("kms_master_key_id")
            if key:
                return str(key)
    return None


def _fold_attachments(plan: PlanSummary) -> None:
    """Copy settings held on child resources onto the resource they configure.

    AWS provider v4+ moves a bucket's ACL, versioning and encryption into
    separate `aws_s3_bucket_*` resources, and Azure models a container's
    access level on the container. A rule judging the bucket or storage
    account alone would miss them, so they are folded onto the parent before
    rules run. The parent is found through the plan's dependency graph, so
    this only happens for real plans; hand-written fixtures state the setting
    on the parent directly.
    """
    by_addr = {r.address: r for r in plan.resources}

    def parent_of(resource: Resource, parent_type: str) -> Optional[Resource]:
        for target in plan.edges.get(resource.address, []):
            candidate = by_addr.get(target)
            if candidate is not None and candidate.type == parent_type:
                return candidate
        return None

    for resource in plan.resources:
        after = resource.after
        if resource.type == "aws_s3_bucket_acl":
            parent = parent_of(resource, "aws_s3_bucket")
            if parent is not None and after.get("acl"):
                parent.after.setdefault("acl", after["acl"])
        elif resource.type == "aws_s3_bucket_versioning":
            parent = parent_of(resource, "aws_s3_bucket")
            status = _versioning_status(after)
            if parent is not None and status is not None:
                parent.after.setdefault("versioning_enabled", status)
        elif resource.type == "aws_s3_bucket_server_side_encryption_configuration":
            parent = parent_of(resource, "aws_s3_bucket")
            key = _sse_key(after)
            if parent is not None and key:
                parent.after.setdefault("kms_master_key_id", key)
        elif resource.type == "azurerm_storage_container":
            parent = parent_of(resource, "azurerm_storage_account")
            access = str(after.get("container_access_type") or "").lower()
            if parent is not None and access in ("blob", "container"):
                parent.after.setdefault("container_access_type", access)


def _configured_rules(policy: Policy) -> List[Rule]:
    """Apply policy overrides (enable/disable, severity, params) to rules."""
    active: List[Rule] = []
    for registered in all_rules():
        if not policy.is_enabled(registered.id):
            continue
        # The registry holds one shared instance per rule. Configure a copy,
        # so one policy's overrides never leak into the next evaluation
        # (the dashboard runs many evaluations in one process).
        rule = copy.copy(registered)
        rule.severity = policy.severity_for(rule.id, type(rule).severity)
        rule.params = policy.params_for(rule.id, dict(type(rule).params or {}))
        active.append(rule)
    return active


def evaluate_plan(
    plan: PlanSummary,
    policy: Optional[Policy] = None,
) -> GateResult:
    started = time.time()
    policy = policy or load_policy()
    _fold_attachments(plan)
    _link_diagnostics(plan)
    t_rules = time.perf_counter()

    targets: List[Resource] = plan.mutating

    # ---- Layer 1: deterministic rules -------------------------------
    rules = _configured_rules(policy)
    findings: List[Finding] = []
    for resource in targets:
        for rule in rules:
            finding = rule.evaluate(resource)
            if finding:
                findings.append(finding)

    t_reason = time.perf_counter()

    # ---- Layer 2: reasoning over framework intent -------------------
    already: Dict[str, List[str]] = {}
    for finding in findings:
        already.setdefault(finding.resource_address, []).append(finding.title)

    reasoner, note = build_reasoner(policy.reasoner)
    try:
        findings.extend(reasoner.analyse(targets, already))
    except Exception as exc:  # pragma: no cover - the gate must never crash
        note = "reasoning layer error: {}".format(type(exc).__name__)

    # Layer 2b: structural reasoning over the dependency graph. It consumes the
    # Layer-1 findings as evidence, so it runs on the rule results only.
    # Waivers are applied before the graph layer, so an accepted risk is not
    # then re-raised as exposure evidence on a neighbouring resource.
    findings = policy.apply_waivers(findings)
    graph_findings: List[Finding] = []
    graph = None
    if policy.reasoner.enabled and policy.reasoner.provider not in ("none", "disabled"):
        graph = GraphReasoner(plan.edges)
        try:
            rule_findings = [f for f in findings if f.source == "rules"]
            graph_findings = graph.analyse_graph(targets, rule_findings)
            findings.extend(graph_findings)
        except Exception as exc:  # pragma: no cover - never crash the gate
            note = "graph reasoning error: {}".format(type(exc).__name__)
    t_graph = time.perf_counter()

    t_policy = time.perf_counter()

    # ---- Layer 3: policy --------------------------------------------
    findings = policy.apply_waivers(findings)
    findings.sort(
        key=lambda f: (-f.severity.rank, f.source != "rules", f.resource_address)
    )
    verdict = policy.decide(findings)

    t_done = time.perf_counter()

    by_pillar = Counter(f.pillar.value for f in findings if not f.waived)
    by_severity = Counter(f.severity.value for f in findings if not f.waived)
    stats: Dict[str, object] = {
        "rules_evaluated": len(rules),
        "findings_total": len(findings),
        "findings_waived": sum(1 for f in findings if f.waived),
        "findings_from_rules": sum(1 for f in findings if f.source == "rules"),
        "findings_from_reasoner": sum(1 for f in findings if f.source == "reasoner"),
        "by_pillar": dict(by_pillar),
        "by_severity": dict(by_severity),
        "providers": [p.value for p in plan.providers],
        "expired_waivers": [w.rule_id for w in policy.expired_waivers()],
        # Measured, not estimated: wall time spent in each layer (ms).
        "stage_ms": {
            "layer1_rules": round((t_reason - t_rules) * 1000, 2),
            "layer2_reasoning": round((t_graph - t_reason) * 1000, 2),
            "layer3_policy": round((t_done - t_policy) * 1000, 2),
        },
        "resources_evaluated": len(targets),
    }
    if note:
        stats["reasoner_note"] = note
    if graph is not None:
        stats["graph_nodes"] = graph.nodes_seen
        stats["graph_edges"] = graph.edges_used
        stats["findings_from_graph"] = len(graph_findings)
        stats["graph_model"] = graph.model
    if hasattr(reasoner, "stats"):
        stats.update(reasoner.stats())  # type: ignore[attr-defined]

    return GateResult(
        verdict=verdict,
        findings=findings,
        plan=plan,
        reasoner_used=reasoner.name,
        duration_ms=int((time.time() - started) * 1000),
        stats=stats,
    )


def evaluate_file(plan_path: str, policy_path: Optional[str] = None) -> GateResult:
    return evaluate_plan(load_plan(plan_path), load_policy(policy_path))
