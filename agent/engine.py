"""The gate engine: plan in, verdict out.

Pipeline position:

    terraform plan -> plan.json -> [ENGINE] -> pass / remediate / block
                                       |
                                       +-- Layer 1: deterministic CAF/WAF rules
                                       +-- Layer 2: reasoning over framework intent
                                       +-- Layer 3: policy (thresholds + waivers)
"""
from __future__ import annotations

import time
from collections import Counter
from typing import Dict, List, Optional

from .config import Policy, load_policy
from .models import Finding, GateResult, PlanSummary, Resource, Verdict
from .plan_parser import load_plan
from .reasoner import build_reasoner
from .rules.base import Rule, all_rules


def _link_diagnostics(plan: PlanSummary) -> None:
    """Mark resources that a diagnostic setting in this plan already covers.

    Terraform expresses this as a separate resource pointing back via
    `target_resource_id`, so the check is inherently cross-resource --
    a rule looking at one resource in isolation could never see it. The
    engine resolves it before rules run.
    """
    covered: set = set()
    for resource in plan.resources:
        if "diagnostic" not in resource.type and "log" not in resource.type:
            continue
        target = resource.after.get("target_resource_id")
        if isinstance(target, str) and target:
            covered.add(target)
        # Unresolved references appear as null; fall back to the plan
        # dependency name embedded in the resource address.
        name = resource.name or ""
        if name:
            covered.add(name)

    for resource in plan.resources:
        if resource.name and resource.name in covered:
            resource.after["_has_diagnostics"] = True
        rid = resource.after.get("id")
        if isinstance(rid, str) and rid in covered:
            resource.after["_has_diagnostics"] = True


def _configured_rules(policy: Policy) -> List[Rule]:
    """Apply policy overrides (enable/disable, severity, params) to rules."""
    active: List[Rule] = []
    for rule in all_rules():
        if not policy.is_enabled(rule.id):
            continue
        rule.severity = policy.severity_for(rule.id, rule.severity)
        rule.params = policy.params_for(rule.id, dict(type(rule).params or {}))
        active.append(rule)
    return active


def evaluate_plan(
    plan: PlanSummary,
    policy: Optional[Policy] = None,
) -> GateResult:
    started = time.time()
    policy = policy or load_policy()
    _link_diagnostics(plan)

    targets: List[Resource] = plan.mutating

    # ---- Layer 1: deterministic rules -------------------------------
    rules = _configured_rules(policy)
    findings: List[Finding] = []
    for resource in targets:
        for rule in rules:
            finding = rule.evaluate(resource)
            if finding:
                findings.append(finding)

    # ---- Layer 2: reasoning over framework intent -------------------
    already: Dict[str, List[str]] = {}
    for finding in findings:
        already.setdefault(finding.resource_address, []).append(finding.title)

    reasoner, note = build_reasoner(policy.reasoner)
    try:
        findings.extend(reasoner.analyse(targets, already))
    except Exception as exc:  # pragma: no cover - the gate must never crash
        note = "reasoning layer error: {}".format(type(exc).__name__)

    # ---- Layer 3: policy --------------------------------------------
    findings = policy.apply_waivers(findings)
    findings.sort(
        key=lambda f: (-f.severity.rank, f.source != "rules", f.resource_address)
    )
    verdict = policy.decide(findings)

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
    }
    if note:
        stats["reasoner_note"] = note
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
