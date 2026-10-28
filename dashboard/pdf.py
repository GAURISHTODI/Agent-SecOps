"""Minimal PDF writer for gate reports (standard library only).

Just enough of the PDF format for a readable text report: A4 pages, the
built-in Helvetica fonts, word wrapping and pagination. No images, no
fonts to embed, so there is nothing to install.
"""
from __future__ import annotations

import textwrap
from typing import Any, Dict, List, Tuple

PAGE_W, PAGE_H = 595, 842
MARGIN = 48
LEADING = 1.35

# (r, g, b) per severity, used for the severity label
_SEV = {
    "critical": (0.64, 0.07, 0.11),
    "high": (0.76, 0.25, 0.05),
    "medium": (0.63, 0.38, 0.03),
    "low": (0.11, 0.30, 0.85),
    "info": (0.28, 0.33, 0.41),
}
_VERDICT = {"block": (0.64, 0.07, 0.11), "remediate": (0.63, 0.38, 0.03), "pass": (0.08, 0.50, 0.24)}


def _esc(text: str) -> str:
    text = text.encode("latin-1", "replace").decode("latin-1")
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class _Doc:
    def __init__(self) -> None:
        self.pages: List[List[str]] = [[]]
        self.y = PAGE_H - MARGIN

    def _need(self, height: float) -> None:
        if self.y - height < MARGIN:
            self.pages.append([])
            self.y = PAGE_H - MARGIN

    def line(self, text: str, size: float = 9.5, bold: bool = False,
             color: Tuple[float, float, float] = (0.1, 0.1, 0.1), indent: float = 0) -> None:
        h = size * LEADING
        self._need(h)
        self.y -= h
        font = "F2" if bold else "F1"
        r, g, b = color
        self.pages[-1].append(
            "BT /{} {} Tf {:.2f} {:.2f} {:.2f} rg {} {:.1f} Td ({}) Tj ET".format(
                font, size, r, g, b, MARGIN + indent, self.y, _esc(text)))

    def wrap(self, text: str, size: float = 9.5, indent: float = 0, bold: bool = False,
             color: Tuple[float, float, float] = (0.1, 0.1, 0.1)) -> None:
        width = int((PAGE_W - 2 * MARGIN - indent) / (size * 0.5))
        for para in str(text).split("\n"):
            for chunk in textwrap.wrap(para, width, break_long_words=True) or [""]:
                self.line(chunk, size, bold, color, indent)

    def gap(self, h: float = 6) -> None:
        self.y -= h

    def rule(self) -> None:
        self._need(6)
        self.y -= 4
        self.pages[-1].append("0.75 G 0.5 w {} {:.1f} m {} {:.1f} l S".format(
            MARGIN, self.y, PAGE_W - MARGIN, self.y))
        self.y -= 4

    def render(self) -> bytes:
        objs: List[bytes] = []

        def add(body: str) -> int:
            objs.append(body.encode("latin-1"))
            return len(objs)

        add("<< /Type /Catalog /Pages 2 0 R >>")
        add("")  # pages placeholder (object 2)
        f1 = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        f2 = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
        kids = []
        total = len(self.pages)
        for n, ops in enumerate(self.pages, 1):
            ops = ops + ["BT /F1 8 Tf 0.45 g {} 28 Td (Agent SecOps  -  page {} of {}) Tj ET".format(
                MARGIN, n, total)]
            stream = "\n".join(ops)
            c = add("<< /Length {} >>\nstream\n{}\nendstream".format(len(stream.encode("latin-1")), stream))
            p = add("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {} {}] /Contents {} 0 R "
                    "/Resources << /Font << /F1 {} 0 R /F2 {} 0 R >> >> >>".format(
                        PAGE_W, PAGE_H, c, f1, f2))
            kids.append("{} 0 R".format(p))
        objs[1] = "<< /Type /Pages /Kids [{}] /Count {} >>".format(" ".join(kids), len(kids)).encode()

        out = bytearray(b"%PDF-1.4\n")
        offsets = []
        for i, body in enumerate(objs, 1):
            offsets.append(len(out))
            out += "{} 0 obj\n".format(i).encode() + body + b"\nendobj\n"
        xref = len(out)
        out += "xref\n0 {}\n0000000000 65535 f \n".format(len(objs) + 1).encode()
        for off in offsets:
            out += "{:010d} 00000 n \n".format(off).encode()
        out += "trailer\n<< /Size {} /Root 1 0 R >>\nstartxref\n{}\n%%EOF\n".format(
            len(objs) + 1, xref).encode()
        return bytes(out)


def build_report_pdf(result: Dict[str, Any]) -> bytes:
    """Render a gate result (the dashboard's JSON payload) as a PDF report."""
    d = _Doc()
    stats = result.get("stats", {}) or {}
    findings = [f for f in result.get("findings", []) if not f.get("waived")]
    verdict = str(result.get("verdict", "pass"))

    d.line("Agent SecOps - CAF/WAF compliance report", 16, True)
    d.gap(4)
    d.line("VERDICT: {}".format(verdict.upper()), 13, True, _VERDICT.get(verdict, (0, 0, 0)))
    d.gap(2)
    d.wrap("Plan: {}   |   Source: {}   |   SHA-256: {}".format(
        result.get("plan_name", ""), result.get("source", ""),
        str(result.get("plan_sha256", ""))[:12] or "n/a"), 9)
    d.wrap("Generated: {}   |   Reasoning layer: {}".format(
        result.get("generated_at", ""), result.get("reasoner", "")), 9)
    d.wrap("{} resources, {} active findings ({} from rules, {} from reasoning, {} waived)".format(
        result.get("resources_evaluated", 0), len(findings),
        stats.get("findings_from_rules", 0), stats.get("findings_from_reasoner", 0),
        stats.get("findings_waived", 0)), 9)
    d.rule()

    by_pillar = stats.get("by_pillar", {}) or {}
    if by_pillar:
        d.line("Findings by framework pillar", 11, True)
        for name, n in sorted(by_pillar.items(), key=lambda kv: -kv[1]):
            d.line("{}: {}".format(name, n), 9.5, indent=10)
        d.rule()

    d.line("Findings", 11, True)
    d.gap(3)
    if not findings:
        d.line("No CAF or WAF violations in this plan.", 10)
    for f in findings:
        sev = str(f.get("severity", "info"))
        d.line("[{}]  {}  -  {}".format(sev.upper(), f.get("rule_id", ""), f.get("title", "")),
               10, True, _SEV.get(sev, (0, 0, 0)))
        d.wrap("Resource: {}   Pillar: {}   Source: {}".format(
            f.get("resource", ""), f.get("pillar", ""),
            "rule" if f.get("source") == "rules"
            else "reasoning ({}%)".format(int(float(f.get("confidence", 0)) * 100))), 9, 10)
        d.wrap(f.get("explanation", ""), 9.5, 10)
        d.wrap("Fix: " + str(f.get("remediation", "")), 9.5, 10)
        if f.get("terraform_fix"):
            for ln in str(f["terraform_fix"]).split("\n"):
                d.line(ln, 8.5, False, (0.2, 0.2, 0.2), 20)
        d.gap(7)

    d.rule()
    d.wrap("Rules map to the Microsoft Cloud Adoption Framework and Azure Well-Architected "
           "Framework. Applying them to AWS and GCP resources extends the intent of those "
           "frameworks to equivalent resource kinds.", 8)
    return d.render()
