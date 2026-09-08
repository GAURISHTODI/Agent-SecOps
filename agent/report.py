"""Report rendering.

Three audiences, three formats:
  * Markdown -- the human on the pull request (the project's headline output)
  * JSON     -- machines, dashboards, and the evaluation harness
  * SARIF    -- GitHub's Security tab, so findings become tracked alerts

The report requirement from the project brief is explicit: show which
rule/pillar was violated and a suggested fix, not just a fail flag.
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Dict, List

from .models import Finding, GateResult, Severity, Verdict

_VERDICT_BANNER = {
    Verdict.PASS: ("PASS", "Deployment approved -- terraform apply may proceed."),
    Verdict.REMEDIATE: (
        "REMEDIATE",
        "Deployment allowed with required follow-up -- fix the findings below.",
    ),
    Verdict.BLOCK: (
        "BLOCK",
        "Deployment halted -- non-compliant resources must be fixed before apply.",
    ),
}

_SEVERITY_ICON = {
    Severity.CRITICAL: "[CRITICAL]",
    Severity.HIGH: "[HIGH]",
    Severity.MEDIUM: "[MEDIUM]",
    Severity.LOW: "[LOW]",
    Severity.INFO: "[INFO]",
}


def _group_by_resource(findings: List[Finding]) -> Dict[str, List[Finding]]:
    grouped: Dict[str, List[Finding]] = defaultdict(list)
    for f in findings:
        grouped[f.resource_address].append(f)
    return grouped


def render_markdown(result: GateResult) -> str:
    label, message = _VERDICT_BANNER[result.verdict]
    stats = result.stats
    lines: List[str] = []

    lines.append("## Agent SecOps -- CAF/WAF Compliance Gate")
    lines.append("")
    lines.append("**Verdict: {}** -- {}".format(label, message))
    lines.append("")
    lines.append(
        "| Resources evaluated | Findings | From rules | From reasoning | Waived | Time |"
    )
    lines.append("|---|---|---|---|---|---|")
    lines.append(
        "| {} | {} | {} | {} | {} | {} ms |".format(
            len(result.plan.mutating),
            stats.get("findings_total", 0),
            stats.get("findings_from_rules", 0),
            stats.get("findings_from_reasoner", 0),
            stats.get("findings_waived", 0),
            result.duration_ms,
        )
    )
    lines.append("")

    active = result.active
    if not active:
        lines.append("No CAF or WAF violations found in this plan.")
        lines.append("")
        lines.append(
            "_Checked {} resource(s) against {} deterministic rules plus the "
            "`{}` reasoning layer._".format(
                len(result.plan.mutating),
                stats.get("rules_evaluated", 0),
                result.reasoner_used,
            )
        )
        return "\n".join(lines)

    # Pillar summary -- the brief requires mapping every finding to a pillar.
    by_pillar = stats.get("by_pillar", {}) or {}
    if by_pillar:
        lines.append("### Violations by framework pillar")
        lines.append("")
        lines.append("| Pillar | Findings |")
        lines.append("|---|---|")
        for pillar, count in sorted(
            by_pillar.items(), key=lambda kv: (-kv[1], kv[0])
        ):
            lines.append("| `{}` | {} |".format(pillar, count))
        lines.append("")

    lines.append("### Findings")
    lines.append("")
    for address, items in _group_by_resource(active).items():
        lines.append("#### `{}`".format(address))
        lines.append("")
        for f in items:
            origin = (
                "deterministic rule"
                if f.source == "rules"
                else "reasoning layer (confidence {:.0%})".format(f.confidence)
            )
            lines.append(
                "- **{} {}** &mdash; `{}` &middot; `{}`".format(
                    _SEVERITY_ICON[f.severity], f.title, f.rule_id, f.pillar.value
                )
            )
            lines.append("  - {}".format(f.explanation))
            lines.append("  - _Fix:_ {}".format(f.remediation))
            if f.terraform_fix:
                lines.append("")
                lines.append("    ```hcl")
                for snippet_line in f.terraform_fix.splitlines():
                    lines.append("    {}".format(snippet_line))
                lines.append("    ```")
            lines.append("  - _Source: {}_".format(origin))
        lines.append("")

    waived = [f for f in result.findings if f.waived]
    if waived:
        lines.append("<details><summary>{} waived finding(s)</summary>".format(len(waived)))
        lines.append("")
        for f in waived:
            lines.append(
                "- `{}` on `{}` -- {}".format(
                    f.rule_id, f.resource_address, f.waiver_reason
                )
            )
        lines.append("")
        lines.append("</details>")
        lines.append("")

    expired = stats.get("expired_waivers") or []
    if expired:
        lines.append(
            "> **Note:** {} waiver(s) have expired and are no longer "
            "suppressing findings: {}".format(len(expired), ", ".join(expired))
        )
        lines.append("")

    note = stats.get("reasoner_note")
    if note:
        lines.append("> _Reasoning layer: {}_".format(note))
        lines.append("")

    lines.append(
        "_Generated by Agent SecOps using {} deterministic rules and the `{}` "
        "reasoning layer._".format(
            stats.get("rules_evaluated", 0), result.reasoner_used
        )
    )
    return "\n".join(lines)


def render_json(result: GateResult) -> str:
    return json.dumps(result.to_dict(), indent=2)


def render_sarif(result: GateResult) -> str:
    """SARIF 2.1.0 so findings land in GitHub's Security tab as alerts."""
    level_map = {
        Severity.CRITICAL: "error",
        Severity.HIGH: "error",
        Severity.MEDIUM: "warning",
        Severity.LOW: "note",
        Severity.INFO: "note",
    }
    seen: Dict[str, Dict] = {}
    results = []
    for f in result.active:
        if f.rule_id not in seen:
            seen[f.rule_id] = {
                "id": f.rule_id,
                "name": f.title,
                "shortDescription": {"text": f.title},
                "fullDescription": {"text": f.remediation},
                "properties": {"pillar": f.pillar.value, "framework": f.pillar.framework},
            }
        results.append(
            {
                "ruleId": f.rule_id,
                "level": level_map[f.severity],
                "message": {
                    "text": "{} [{}] {} Fix: {}".format(
                        f.resource_address, f.pillar.value, f.explanation, f.remediation
                    )
                },
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": "plan.json"},
                            "region": {"startLine": 1},
                        }
                    }
                ],
                "partialFingerprints": {
                    "resourceRule": "{}::{}".format(f.resource_address, f.rule_id)
                },
            }
        )

    return json.dumps(
        {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "Agent SecOps",
                            "informationUri": "https://github.com/",
                            "rules": list(seen.values()),
                        }
                    },
                    "results": results,
                }
            ],
        },
        indent=2,
    )


def render_console(result: GateResult) -> str:
    """Terse output for the CI log."""
    label, _ = _VERDICT_BANNER[result.verdict]
    lines = [
        "Agent SecOps: {} ({} resource(s), {} finding(s), {} ms)".format(
            label,
            len(result.plan.mutating),
            len(result.active),
            result.duration_ms,
        )
    ]
    for f in result.active:
        lines.append(
            "  {:<10} {:<14} {:<28} {}".format(
                f.severity.value.upper(), f.rule_id, f.pillar.value, f.resource_address
            )
        )
        lines.append("             {}".format(f.explanation))
    return "\n".join(lines)
