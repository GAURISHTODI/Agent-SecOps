"""Reasoning layer -- Layer 2 of the gate.

The deterministic rules answer "does this break a rule someone wrote?".
The reasoner answers the question the project exists for: "does this break
CAF/WAF *intent* that nobody ever turned into a rule?"

Both concrete reasoners (offline heuristic, LLM) share this interface and
this context builder, so the pipeline behaves identically whether or not
an LLM endpoint is available -- which is what keeps CI free by default.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import yaml

from ..models import Finding, Pillar, Resource, Severity

KB_PATH = Path(__file__).resolve().parent.parent / "knowledge" / "caf_waf_kb.yaml"

# Fields that are noise for reasoning, or that must never leave the runner.
_DROP_FIELDS = {
    "id", "timeouts", "tags_all", "arn", "self_link", "fqdn",
    "primary_blob_connection_string", "secondary_blob_connection_string",
    "primary_access_key", "secondary_access_key", "primary_connection_string",
    "secondary_connection_string", "administrator_login_password",
    "admin_password", "password", "client_secret", "secret_value",
}
_MAX_VALUE_LEN = 160


def load_kb() -> Dict[str, Any]:
    return yaml.safe_load(KB_PATH.read_text(encoding="utf-8")) or {}


def redact(value: Any) -> Any:
    """Shrink and sanitise a planned attribute before it is reasoned over.

    Two jobs: keep secrets off the wire when an external LLM is used, and
    keep the prompt small, because prompt size is literally the cost of a
    gate run.
    """
    if isinstance(value, dict):
        return {
            k: redact(v)
            for k, v in value.items()
            if k not in _DROP_FIELDS and v is not None
        }
    if isinstance(value, list):
        return [redact(v) for v in value[:5]]
    if isinstance(value, str) and len(value) > _MAX_VALUE_LEN:
        return value[:_MAX_VALUE_LEN] + "...(truncated)"
    return value


def summarise(resource: Resource) -> Dict[str, Any]:
    """Compact, redacted view of one planned resource."""
    return {
        "address": resource.address,
        "type": resource.type,
        "cloud": resource.provider.value,
        "kind": resource.kind.value,
        "action": resource.action.value,
        "config": redact(resource.after),
    }


def kb_context(kind: str, kb: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve only the framework guidance relevant to this resource kind.

    This is the retrieval step: instead of pasting the whole CAF/WAF corpus
    into every prompt, we look up the handful of pillars and watch-points
    indexed against this kind.
    """
    focus = (kb.get("kind_focus") or {}).get(kind, {})
    pillar_names: Sequence[str] = focus.get("pillars", []) or []
    pillars = kb.get("pillars") or {}
    return {
        "pillars": {
            name: pillars.get(name, {}).get("principles", [])
            for name in pillar_names
        },
        "watch_for": focus.get("watch_for", []),
    }


class Reasoner:
    """Base class for Layer 2."""

    name = "base"

    def analyse(
        self,
        resources: List[Resource],
        already_found: Dict[str, List[str]],
    ) -> List[Finding]:
        """Return advisory findings for concerns the rules did not raise.

        `already_found` maps a resource address to the rule titles that
        already fired on it, so the reasoner never duplicates Layer 1.
        """
        raise NotImplementedError


def make_finding(
    resource_address: str,
    title: str,
    pillar_name: str,
    severity_name: str,
    explanation: str,
    remediation: str,
    confidence: float,
    source: str,
    terraform_fix: Optional[str] = None,
    rule_id: str = "REASONER",
) -> Optional[Finding]:
    """Build a Finding from loosely-typed reasoner output, defensively.

    LLM output is untrusted structurally: an unknown pillar or severity
    must degrade gracefully rather than crash the pipeline gate.
    """
    try:
        pillar = Pillar(pillar_name)
    except ValueError:
        pillar = Pillar.WAF_SECURITY
    try:
        severity = Severity(str(severity_name).lower())
    except ValueError:
        severity = Severity.LOW
    if not explanation:
        return None
    return Finding(
        rule_id=rule_id,
        title=title or "Framework-intent concern",
        pillar=pillar,
        severity=severity,
        resource_address=resource_address,
        explanation=explanation,
        remediation=remediation or "Review against the cited pillar guidance.",
        source=source,
        confidence=max(0.0, min(1.0, float(confidence))),
        terraform_fix=terraform_fix,
    )


def parse_json_block(text: str) -> Any:
    """Extract a JSON array/object from a model response.

    Models sometimes wrap JSON in prose or a fenced block; be forgiving.
    """
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    start = min(
        [i for i in (text.find("["), text.find("{")) if i != -1] or [-1]
    )
    if start == -1:
        return []
    end = max(text.rfind("]"), text.rfind("}"))
    if end == -1:
        return []
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
