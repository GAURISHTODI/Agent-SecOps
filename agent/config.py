"""Policy configuration: thresholds, rule overrides and waivers.

An organisation tunes the gate here rather than by editing Python. That
matters for the research claim: the deterministic layer stays fixed and
auditable while the *policy* around it is per-org configuration.
"""
from __future__ import annotations

import datetime as _dt
import fnmatch
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .models import Finding, Severity, Verdict

DEFAULT_POLICY_PATH = Path(__file__).resolve().parent.parent / "policies" / "policy.yaml"


@dataclass
class Waiver:
    """A time-boxed exception, so 'accepted risk' cannot silently be forever."""

    rule_id: str
    resource: str = "*"
    reason: str = ""
    expires: Optional[str] = None

    def is_expired(self, today: Optional[_dt.date] = None) -> bool:
        if not self.expires:
            return False
        try:
            end = _dt.date.fromisoformat(str(self.expires))
        except ValueError:
            return False
        return (today or _dt.date.today()) > end

    def matches(self, finding: Finding) -> bool:
        if self.rule_id not in ("*", finding.rule_id):
            return False
        return fnmatch.fnmatch(finding.resource_address, self.resource)


@dataclass
class ReasonerConfig:
    provider: str = "offline"       # offline | azure_openai | anthropic
    model: str = "gpt-4o-mini"
    max_resources: int = 12         # hard cap on how many resources reach the LLM
    max_output_tokens: int = 900
    temperature: float = 0.0
    min_confidence: float = 0.6     # below this, a finding is dropped as noise
    cache_dir: str = ".secops_cache"
    enabled: bool = True


@dataclass
class Policy:
    block_at: Severity = Severity.HIGH
    remediate_at: Severity = Severity.MEDIUM
    fail_on_reasoner_findings: bool = False
    rule_overrides: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    waivers: List[Waiver] = field(default_factory=list)
    reasoner: ReasonerConfig = field(default_factory=ReasonerConfig)

    # ---- rule tuning ------------------------------------------------
    def override_for(self, rule_id: str) -> Dict[str, Any]:
        return self.rule_overrides.get(rule_id, {})

    def is_enabled(self, rule_id: str) -> bool:
        return bool(self.override_for(rule_id).get("enabled", True))

    def severity_for(self, rule_id: str, default: Severity) -> Severity:
        raw = self.override_for(rule_id).get("severity")
        if not raw:
            return default
        try:
            return Severity(str(raw).lower())
        except ValueError:
            return default

    def params_for(self, rule_id: str, defaults: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(defaults)
        merged.update(self.override_for(rule_id).get("params", {}) or {})
        return merged

    # ---- waivers ----------------------------------------------------
    def apply_waivers(self, findings: List[Finding]) -> List[Finding]:
        for finding in findings:
            for waiver in self.waivers:
                if waiver.matches(finding) and not waiver.is_expired():
                    finding.waived = True
                    finding.waiver_reason = waiver.reason or "waived by policy"
                    break
        return findings

    def expired_waivers(self) -> List[Waiver]:
        return [w for w in self.waivers if w.is_expired()]

    # ---- verdict ----------------------------------------------------
    def decide(self, findings: List[Finding]) -> Verdict:
        """Aggregate findings into one gate decision.

        A finding only escalates the verdict if it is active (not waived)
        and, when it came from the reasoning layer, if the policy trusts
        the reasoner enough to fail a build on it.
        """
        verdict = Verdict.PASS
        for f in findings:
            if f.waived:
                continue
            if f.source == "reasoner" and not self.fail_on_reasoner_findings:
                # Advisory only: reported in full, but never blocks the pipeline.
                if verdict == Verdict.PASS and f.severity.rank >= self.remediate_at.rank:
                    verdict = Verdict.REMEDIATE
                continue
            if f.severity.rank >= self.block_at.rank:
                return Verdict.BLOCK
            if f.severity.rank >= self.remediate_at.rank:
                verdict = Verdict.REMEDIATE
        return verdict


def _severity(value: Any, default: Severity) -> Severity:
    try:
        return Severity(str(value).lower())
    except (ValueError, AttributeError):
        return default


def load_policy(path: Optional[str] = None) -> Policy:
    """Read policy.yaml, falling back to safe built-in defaults."""
    target = Path(path) if path else DEFAULT_POLICY_PATH
    if not target.exists():
        return Policy()
    data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}

    thresholds = data.get("thresholds", {}) or {}
    reasoner_raw = data.get("reasoner", {}) or {}
    reasoner = ReasonerConfig(
        provider=str(reasoner_raw.get("provider", "offline")),
        model=str(reasoner_raw.get("model", "gpt-4o-mini")),
        max_resources=int(reasoner_raw.get("max_resources", 12)),
        max_output_tokens=int(reasoner_raw.get("max_output_tokens", 900)),
        temperature=float(reasoner_raw.get("temperature", 0.0)),
        min_confidence=float(reasoner_raw.get("min_confidence", 0.6)),
        cache_dir=str(reasoner_raw.get("cache_dir", ".secops_cache")),
        enabled=bool(reasoner_raw.get("enabled", True)),
    )
    # Environment always wins, so CI can force the zero-cost path.
    env_provider = os.environ.get("SECOPS_REASONER")
    if env_provider:
        reasoner.provider = env_provider

    waivers = [
        Waiver(
            rule_id=str(w.get("rule_id", "*")),
            resource=str(w.get("resource", "*")),
            reason=str(w.get("reason", "")),
            expires=w.get("expires"),
        )
        for w in (data.get("waivers") or [])
    ]

    return Policy(
        block_at=_severity(thresholds.get("block_at"), Severity.HIGH),
        remediate_at=_severity(thresholds.get("remediate_at"), Severity.MEDIUM),
        fail_on_reasoner_findings=bool(
            thresholds.get("fail_on_reasoner_findings", False)
        ),
        rule_overrides=data.get("rules", {}) or {},
        waivers=waivers,
        reasoner=reasoner,
    )
