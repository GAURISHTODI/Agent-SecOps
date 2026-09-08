"""LLM reasoner -- the optional, paid Layer 2.

Cost is treated as a first-class design constraint, because this project
runs on a fixed pool of student Azure credits. Four mechanisms keep spend
near zero:

  1. Triage      - only resources a rule could not fully judge are sent.
  2. Cap         - `max_resources` hard-limits how many reach the model.
  3. Redaction   - the prompt carries a shrunk, secret-free config, not
                   the raw plan (prompt size *is* the bill).
  4. Disk cache  - a plan whose content hash was already judged is never
                   re-sent, so re-runs of the same PR are free.

If no endpoint or key is configured the class refuses to construct, and
the engine silently falls back to the offline reasoner.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..models import Finding, Resource
from .base import Reasoner, kb_context, load_kb, make_finding, parse_json_block, summarise

SYSTEM_PROMPT = """You are a cloud governance reviewer for a CI/CD deployment gate.

You are given resources from a Terraform plan that is about to be applied,
plus the Cloud Adoption Framework (CAF) and Well-Architected Framework (WAF)
principles relevant to each resource.

A deterministic rule engine has ALREADY checked these resources for known
violations, and its findings are listed to you. Your job is the opposite:
report only concerns that framework guidance implies but that no listed rule
caught -- architectural intent, risky combinations of settings, and context
that a static rule cannot express.

Rules of engagement:
- Never repeat a concern already listed under "already_reported".
- Judge only what is visible in the config. Do not speculate about resources
  that are not shown.
- An unknown/null value means Terraform will compute it at apply time; never
  report it as a violation.
- Prefer few, high-quality findings. Zero findings is a valid answer.

Reply with ONLY a JSON array. Each element:
{"resource": "<address>", "title": "<short title>",
 "pillar": "<one of the pillar names given to you>",
 "severity": "critical|high|medium|low",
 "explanation": "<why this violates the pillar, 1-2 sentences>",
 "remediation": "<what to change>",
 "terraform_fix": "<optional HCL snippet>",
 "confidence": <0.0-1.0>}"""


class LLMUnavailable(RuntimeError):
    """Raised when no usable endpoint/credentials are configured."""


def _hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


class LLMReasoner(Reasoner):
    """Talks to Azure OpenAI (default) or the Anthropic API.

    Uses urllib rather than a vendor SDK so the gate has no runtime
    dependency to install on the CI runner beyond PyYAML.
    """

    name = "llm"

    def __init__(
        self,
        provider: str = "azure_openai",
        model: str = "gpt-4o-mini",
        max_resources: int = 12,
        max_output_tokens: int = 900,
        temperature: float = 0.0,
        min_confidence: float = 0.6,
        cache_dir: str = ".secops_cache",
    ) -> None:
        self.provider = provider
        self.model = model
        self.max_resources = max_resources
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature
        self.min_confidence = min_confidence
        self.cache_dir = Path(cache_dir)
        self.kb = load_kb()
        self.tokens_used = 0
        self.cache_hits = 0
        self.calls = 0

        if provider == "azure_openai":
            self.endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
            self.key = os.environ.get("AZURE_OPENAI_API_KEY", "")
            self.deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", model)
            self.api_version = os.environ.get(
                "AZURE_OPENAI_API_VERSION", "2024-10-21"
            )
            if not self.endpoint or not self.key:
                raise LLMUnavailable(
                    "AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY must be set "
                    "to use the azure_openai reasoner."
                )
        elif provider == "anthropic":
            self.key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not self.key:
                raise LLMUnavailable("ANTHROPIC_API_KEY must be set.")
        else:
            raise LLMUnavailable("Unknown LLM provider: {}".format(provider))

    # ---- prompt construction ----------------------------------------
    def _build_payload(
        self, resources: List[Resource], already_found: Dict[str, List[str]]
    ) -> Dict[str, Any]:
        items = []
        for resource in resources:
            context = kb_context(resource.kind.value, self.kb)
            items.append(
                {
                    "resource": summarise(resource),
                    "framework_guidance": context,
                    "already_reported": already_found.get(resource.address, []),
                }
            )
        return {"resources_under_review": items}

    def _triage(self, resources: List[Resource]) -> List[Resource]:
        """Choose which resources are worth paying to reason about.

        Resources whose kind carries no framework focus in the KB (e.g. a
        plain resource group) are dropped first, then the list is capped.
        """
        focus = self.kb.get("kind_focus") or {}
        ranked = sorted(
            resources,
            key=lambda r: (r.kind.value not in focus, len(r.after)),
        )
        return [r for r in ranked if r.kind.value in focus][: self.max_resources]

    # ---- transport ---------------------------------------------------
    def _post(self, url: str, headers: Dict[str, str], body: Dict[str, Any]) -> Dict[str, Any]:
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.loads(response.read().decode("utf-8"))

    def _call(self, user_content: str) -> Tuple[str, int]:
        self.calls += 1
        if self.provider == "azure_openai":
            url = "{}/openai/deployments/{}/chat/completions?api-version={}".format(
                self.endpoint, self.deployment, self.api_version
            )
            data = self._post(
                url,
                {"Content-Type": "application/json", "api-key": self.key},
                {
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    "temperature": self.temperature,
                    "max_tokens": self.max_output_tokens,
                    "response_format": {"type": "json_object"},
                },
            )
            text = data["choices"][0]["message"]["content"]
            used = int((data.get("usage") or {}).get("total_tokens", 0))
            return text, used

        # Anthropic Messages API
        data = self._post(
            "https://api.anthropic.com/v1/messages",
            {
                "Content-Type": "application/json",
                "x-api-key": self.key,
                "anthropic-version": "2023-06-01",
            },
            {
                "model": self.model,
                "max_tokens": self.max_output_tokens,
                "temperature": self.temperature,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_content}],
            },
        )
        text = "".join(
            block.get("text", "") for block in data.get("content", [])
        )
        usage = data.get("usage") or {}
        used = int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))
        return text, used

    # ---- cache -------------------------------------------------------
    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / "{}.json".format(key)

    def _cached(self, key: str) -> Optional[Any]:
        path = self._cache_path(key)
        if not path.exists():
            return None
        try:
            self.cache_hits += 1
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _store(self, key: str, value: Any) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._cache_path(key).write_text(
                json.dumps(value, indent=2), encoding="utf-8"
            )
        except OSError:
            pass  # a read-only runner must not fail the gate over a cache write

    # ---- main entry point --------------------------------------------
    def analyse(
        self,
        resources: List[Resource],
        already_found: Dict[str, List[str]],
    ) -> List[Finding]:
        selected = self._triage(resources)
        if not selected:
            return []

        payload = self._build_payload(selected, already_found)
        user_content = json.dumps(payload, indent=1, sort_keys=True)
        key = _hash(self.model + user_content)

        raw = self._cached(key)
        if raw is None:
            try:
                text, used = self._call(user_content)
            except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as exc:
                # A model outage must degrade the gate, never break it: the
                # deterministic layer has already produced its verdict.
                return [
                    make_finding(
                        resource_address="(gate)",
                        title="LLM reasoning layer unavailable",
                        pillar_name="WAF:OperationalExcellence",
                        severity_name="info",
                        explanation=(
                            "The reasoning layer could not be reached ({}). The "
                            "verdict below rests on the deterministic rule engine "
                            "only.".format(type(exc).__name__)
                        ),
                        remediation="Check the endpoint configuration and secrets.",
                        confidence=1.0,
                        source="reasoner",
                        rule_id="REASON-UNAVAILABLE",
                    )
                ]
            self.tokens_used += used
            raw = parse_json_block(text)
            self._store(key, raw)

        if isinstance(raw, dict):
            raw = raw.get("findings") or raw.get("results") or []
        if not isinstance(raw, list):
            return []

        valid_addresses = {r.address for r in selected}
        findings: List[Finding] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            address = str(item.get("resource", ""))
            if address not in valid_addresses:
                continue  # never let the model invent a resource
            confidence = float(item.get("confidence", 0.5) or 0.5)
            if confidence < self.min_confidence:
                continue
            finding = make_finding(
                resource_address=address,
                title=str(item.get("title", "")),
                pillar_name=str(item.get("pillar", "")),
                severity_name=str(item.get("severity", "low")),
                explanation=str(item.get("explanation", "")),
                remediation=str(item.get("remediation", "")),
                confidence=confidence,
                source="reasoner",
                terraform_fix=item.get("terraform_fix") or None,
                rule_id="REASON-LLM",
            )
            if finding:
                findings.append(finding)
        return findings

    def stats(self) -> Dict[str, Any]:
        return {
            "llm_calls": self.calls,
            "llm_tokens": self.tokens_used,
            "cache_hits": self.cache_hits,
        }
