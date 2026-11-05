"""Layer 4 -- local-LLM advisor (Ollama).

The gate decides; the model explains. This layer runs *after* the verdict is
fixed and only attaches a plain-language explanation and a suggested fix to
findings that the deterministic layers already raised. It cannot add, remove,
waive or re-rate a finding, so a small local model can never change whether a
deployment is blocked.

Guardrails (all in `_validate`):
  - the prompt carries a redacted, truncated view of the one resource;
  - output must be JSON with two short strings, otherwise it is dropped;
  - output that names a Terraform resource not present in the plan is dropped;
  - any error or timeout leaves the finding untouched (no advice, same verdict).
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
from typing import Any, Dict, List, Optional

from .models import Finding, GateResult
from .reasoner.base import parse_json_block, summarise

SYSTEM_PROMPT = (
    "You are a cloud security assistant inside a Terraform CI gate. A rule "
    "engine has already found the issue below; do NOT re-judge it. Explain "
    "in plain words why it matters and give one concrete fix, using only the "
    "resource config shown. Reply with ONLY JSON: "
    '{"summary": "<1-2 sentences>", "fix": "<1-2 sentences or a short HCL line>"}'
)

_MAX_LEN = 400
# Looks like a Terraform address, e.g. aws_s3_bucket.data / azurerm_x.y
_ADDRESS_RE = re.compile(r"\b(?:aws|azurerm|google)_[a-z0-9_]+\.[A-Za-z0-9_\-]+")


class Advisor:
    def __init__(
        self,
        model: str = "qwen2.5:3b",
        host: str = "http://127.0.0.1:11434",
        max_findings: int = 5,
        timeout: float = 60.0,
    ) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.max_findings = max_findings
        self.timeout = timeout

    # ---- model call (kept separate so tests can replace it) ----------
    def _chat(self, prompt: str) -> str:
        body = json.dumps({
            "model": self.model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0, "num_predict": 200},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        }).encode("utf-8")
        req = urllib.request.Request(
            self.host + "/api/chat", data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))["message"]["content"]

    # ---- guardrails ---------------------------------------------------
    @staticmethod
    def _validate(raw: str, known_addresses: set) -> Optional[str]:
        data = parse_json_block(raw)
        if not isinstance(data, dict):
            return None
        summary, fix = data.get("summary"), data.get("fix")
        if not isinstance(summary, str) or not isinstance(fix, str):
            return None
        summary, fix = summary.strip(), fix.strip()
        if not summary or not fix or len(summary) > _MAX_LEN or len(fix) > _MAX_LEN:
            return None
        for addr in _ADDRESS_RE.findall(summary + " " + fix):
            if addr not in known_addresses:
                return None  # hallucinated resource
        return "{} Suggested fix: {}".format(summary, fix)

    # ---- public API ---------------------------------------------------
    def annotate(self, result: GateResult) -> Dict[str, Any]:
        """Attach advice to the top findings. Never changes the verdict."""
        started = time.perf_counter()
        known = {r.address for r in result.plan.resources}
        by_addr = {r.address: r for r in result.plan.resources}
        candidates: List[Finding] = [
            f for f in result.active if f.resource_address in by_addr
        ][: self.max_findings]

        advised = rejected = 0
        note = ""
        for finding in candidates:
            prompt = json.dumps({
                "rule": finding.rule_id,
                "title": finding.title,
                "pillar": finding.pillar.value,
                "why_flagged": finding.explanation,
                "resource": summarise(by_addr[finding.resource_address]),
            })
            try:
                advice = self._validate(self._chat(prompt), known)
            except Exception as exc:  # Ollama down, timeout, bad payload
                note = "advisor unavailable ({}); verdict unaffected".format(
                    type(exc).__name__
                )
                break
            if advice:
                finding.ai_advice = advice
                advised += 1
            else:
                rejected += 1

        stats = {
            "model": self.model,
            "considered": len(candidates),
            "advised": advised,
            "rejected_by_guardrails": rejected,
            "ms": round((time.perf_counter() - started) * 1000),
        }
        if note:
            stats["note"] = note
        result.stats["advisor"] = stats
        return stats
