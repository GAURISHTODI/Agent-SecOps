"""Layer 4 advisor: guardrails and the guarantee that it never moves the verdict."""
from __future__ import annotations

import json
from pathlib import Path

from agent.advisor import Advisor
from agent.engine import evaluate_file

ROOT = Path(__file__).resolve().parent.parent
PLAN = str(ROOT / "examples" / "plans" / "azure_noncompliant.plan.json")
POLICY = str(ROOT / "policies" / "policy.yaml")


class FakeAdvisor(Advisor):
    def __init__(self, reply):
        super().__init__(max_findings=3)
        self.reply = reply

    def _chat(self, prompt):
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def _run(reply):
    from agent.config import load_policy
    from agent.engine import evaluate_plan
    from agent.plan_parser import load_plan

    base = evaluate_file(PLAN, POLICY)
    result = evaluate_plan(load_plan(PLAN), load_policy(POLICY), advisor=FakeAdvisor(reply))
    return base, result


def test_valid_advice_is_attached_and_verdict_unchanged():
    reply = json.dumps({"summary": "Public access exposes data.", "fix": "Disable public access."})
    base, result = _run(reply)
    assert result.verdict is base.verdict
    assert [f.rule_id for f in result.findings] == [f.rule_id for f in base.findings]
    assert result.stats["advisor"]["advised"] == 3
    assert all(f.ai_advice for f in result.active[:3])


def test_malformed_json_is_dropped():
    base, result = _run("not json at all")
    assert result.stats["advisor"]["advised"] == 0
    assert result.stats["advisor"]["rejected_by_guardrails"] == 3
    assert result.verdict is base.verdict


def test_hallucinated_resource_is_dropped():
    reply = json.dumps({"summary": "Fix azurerm_made_up.ghost now.", "fix": "Delete it."})
    _, result = _run(reply)
    assert result.stats["advisor"]["advised"] == 0


def test_oversized_or_wrong_type_output_is_dropped():
    _, result = _run(json.dumps({"summary": "x" * 1000, "fix": "ok"}))
    assert result.stats["advisor"]["advised"] == 0
    _, result = _run(json.dumps({"summary": 5, "fix": ["a"]}))
    assert result.stats["advisor"]["advised"] == 0


def test_ollama_down_falls_back_without_changing_verdict():
    base, result = _run(ConnectionError("refused"))
    assert result.verdict is base.verdict
    assert "unavailable" in result.stats["advisor"]["note"]
    assert not any(f.ai_advice for f in result.findings)
