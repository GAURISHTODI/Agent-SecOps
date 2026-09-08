"""Rule base class and global registry.

A rule is deterministic, cheap and explainable: given one `Resource` it
returns zero or more `Finding`s. This is Layer 1 of the gate -- it costs
nothing to run and produces confidence-1.0 findings. Layer 2 (the
reasoner) only handles what no rule covers.
"""
from __future__ import annotations

from typing import Callable, Dict, Iterable, List, Optional, Sequence

from ..models import Finding, Kind, Pillar, Provider, Resource, Severity

_REGISTRY: List["Rule"] = []


class Rule:
    """One CAF/WAF check.

    Subclasses set the metadata attributes and implement `check`.
    """

    id: str = ""
    title: str = ""
    pillar: Pillar = Pillar.WAF_SECURITY
    severity: Severity = Severity.MEDIUM
    kinds: Sequence[Kind] = ()          # empty = applies to every kind
    providers: Sequence[Provider] = ()  # empty = every provider
    remediation: str = ""
    terraform_fix: Optional[str] = None
    # Human-readable statement of the framework guidance being enforced.
    # This string is also fed to the reasoner so it never re-reports a
    # concern a deterministic rule has already covered.
    rationale: str = ""
    # Tunable knobs an organisation can override from policies/policy.yaml
    # without editing Python (e.g. the list of mandatory tags).
    params: Dict[str, object] = {}

    def param(self, key: str, default: object = None) -> object:
        return self.params.get(key, default)

    def applies_to(self, resource: Resource) -> bool:
        if not resource.is_mutating:
            return False
        if self.kinds and resource.kind not in self.kinds:
            return False
        if self.providers and resource.provider not in self.providers:
            return False
        return True

    def check(self, resource: Resource) -> Optional[str]:
        """Return an explanation string when the resource violates the rule.

        Returning None means the resource is compliant with this rule.
        """
        raise NotImplementedError

    def evaluate(self, resource: Resource) -> Optional[Finding]:
        if not self.applies_to(resource):
            return None
        explanation = self.check(resource)
        if not explanation:
            return None
        return Finding(
            rule_id=self.id,
            title=self.title,
            pillar=self.pillar,
            severity=self.severity,
            resource_address=resource.address,
            explanation=explanation,
            remediation=self.remediation,
            source="rules",
            confidence=1.0,
            terraform_fix=self.terraform_fix,
        )


def register(cls: type) -> type:
    """Class decorator: add a rule to the global registry."""
    instance = cls()
    if not instance.id:
        raise ValueError("Rule {} is missing an id".format(cls.__name__))
    if any(r.id == instance.id for r in _REGISTRY):
        raise ValueError("Duplicate rule id: {}".format(instance.id))
    _REGISTRY.append(instance)
    return cls


def all_rules() -> List[Rule]:
    # Importing the rule modules populates the registry via @register.
    from . import caf, waf  # noqa: F401  (import for side effects)

    return list(_REGISTRY)


def rules_for(resource: Resource) -> List[Rule]:
    return [r for r in all_rules() if r.applies_to(resource)]


# --- small helpers shared by rule modules ------------------------------

def truthy(value: object) -> bool:
    """Terraform renders booleans as bool, but unknown values arrive as None."""
    return value is True or str(value).lower() == "true"


def is_open_cidr(cidr: object) -> bool:
    """True for any CIDR that means 'the entire internet'."""
    return str(cidr) in ("0.0.0.0/0", "::/0", "*", "internet", "any")


def missing_tags(resource: Resource, required: Iterable[str]) -> List[str]:
    present = {k.lower() for k in resource.tags}
    return [t for t in required if t.lower() not in present]
