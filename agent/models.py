"""Core data model for Agent SecOps.

Everything downstream of the plan parser speaks this vocabulary, which is
deliberately cloud-agnostic: a rule is written once against a `Resource`
and works whether the underlying plan came from Azure, AWS or GCP.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class Provider(str, enum.Enum):
    AZURE = "azure"
    AWS = "aws"
    GCP = "gcp"
    UNKNOWN = "unknown"


class Action(str, enum.Enum):
    """What the plan intends to do with a resource."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    REPLACE = "replace"
    NOOP = "no-op"
    READ = "read"


class Kind(str, enum.Enum):
    """Canonical resource kinds.

    Provider-specific types (azurerm_storage_account, aws_s3_bucket,
    google_storage_bucket) collapse into one kind so a single rule covers
    all three clouds.
    """

    OBJECT_STORAGE = "object_storage"
    COMPUTE_INSTANCE = "compute_instance"
    MANAGED_DATABASE = "managed_database"
    NETWORK_FIREWALL = "network_firewall"
    NETWORK_PUBLIC_IP = "network_public_ip"
    SECRET_STORE = "secret_store"
    IAM_BINDING = "iam_binding"
    CONTAINER_PLATFORM = "container_platform"
    RESOURCE_GROUP = "resource_group"
    LOG_WORKSPACE = "log_workspace"
    APP_HOSTING = "app_hosting"
    OTHER = "other"


class Severity(str, enum.Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

    @property
    def rank(self) -> int:
        return {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}[self.value]


class Verdict(str, enum.Enum):
    PASS = "pass"
    REMEDIATE = "remediate"
    BLOCK = "block"

    @property
    def rank(self) -> int:
        return {"pass": 0, "remediate": 1, "block": 2}[self.value]


class Pillar(str, enum.Enum):
    """CAF governance pillars + the six WAF pillars.

    Every finding must map to exactly one of these, because the report is
    required to name the pillar that was violated -- not just fail a flag.
    """

    CAF_GOVERNANCE = "CAF:Governance"
    CAF_LANDING_ZONE = "CAF:LandingZone"
    CAF_COST_MANAGEMENT = "CAF:CostManagement"
    CAF_IDENTITY = "CAF:Identity"
    WAF_SECURITY = "WAF:Security"
    WAF_RELIABILITY = "WAF:Reliability"
    WAF_COST = "WAF:CostOptimization"
    WAF_OPERATIONS = "WAF:OperationalExcellence"
    WAF_PERFORMANCE = "WAF:PerformanceEfficiency"
    # Azure's WAF defines five pillars; AWS adds Sustainability as a sixth.
    # We carry it because it is the pillar that maps to the project's SDG 9
    # claim about resource-efficient infrastructure.
    WAF_SUSTAINABILITY = "WAF:Sustainability"

    @property
    def framework(self) -> str:
        return self.value.split(":", 1)[0]


@dataclass
class Resource:
    """One resource change extracted from a Terraform plan."""

    address: str
    type: str
    name: str
    provider: Provider
    kind: Kind
    action: Action
    after: Dict[str, Any] = field(default_factory=dict)
    before: Dict[str, Any] = field(default_factory=dict)
    module: str = "root"

    # ---- helpers used heavily by rules -------------------------------
    def get(self, path: str, default: Any = None) -> Any:
        """Dotted lookup into the planned (`after`) state.

        Terraform renders nested blocks as single-element lists, so
        `network_rules.default_action` transparently steps into
        `after["network_rules"][0]["default_action"]`.
        """
        node: Any = self.after
        for part in path.split("."):
            if isinstance(node, list):
                node = node[0] if node else None
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        if isinstance(node, list) and len(node) == 1 and isinstance(node[0], dict):
            return node[0]
        return default if node is None else node

    @property
    def tags(self) -> Dict[str, str]:
        raw = self.after.get("tags") or self.after.get("labels") or {}
        if isinstance(raw, list):  # aws-style [{key,value}] tag sets
            return {t.get("key"): t.get("value") for t in raw if isinstance(t, dict)}
        return {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}

    @property
    def is_mutating(self) -> bool:
        return self.action in (Action.CREATE, Action.UPDATE, Action.REPLACE)


@dataclass
class Finding:
    """A single compliance violation, always tied to a pillar."""

    rule_id: str
    title: str
    pillar: Pillar
    severity: Severity
    resource_address: str
    explanation: str
    remediation: str
    source: str = "rules"          # "rules" | "reasoner"
    confidence: float = 1.0        # deterministic rules are 1.0 by definition
    terraform_fix: Optional[str] = None
    waived: bool = False
    waiver_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "title": self.title,
            "pillar": self.pillar.value,
            "framework": self.pillar.framework,
            "severity": self.severity.value,
            "resource": self.resource_address,
            "explanation": self.explanation,
            "remediation": self.remediation,
            "source": self.source,
            "confidence": round(self.confidence, 2),
            "terraform_fix": self.terraform_fix,
            "waived": self.waived,
            "waiver_reason": self.waiver_reason,
        }


@dataclass
class PlanSummary:
    """Everything the parser learned about one plan file."""

    resources: List[Resource]
    terraform_version: str = "unknown"
    format_version: str = "unknown"
    providers: List[Provider] = field(default_factory=list)

    @property
    def mutating(self) -> List[Resource]:
        return [r for r in self.resources if r.is_mutating]


@dataclass
class GateResult:
    """Final output of one gate run."""

    verdict: Verdict
    findings: List[Finding]
    plan: PlanSummary
    reasoner_used: str = "offline"
    duration_ms: int = 0
    stats: Dict[str, Any] = field(default_factory=dict)

    @property
    def active(self) -> List[Finding]:
        return [f for f in self.findings if not f.waived]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "reasoner": self.reasoner_used,
            "duration_ms": self.duration_ms,
            "stats": self.stats,
            "resources_evaluated": len(self.plan.mutating),
            "findings": [f.to_dict() for f in self.findings],
        }
