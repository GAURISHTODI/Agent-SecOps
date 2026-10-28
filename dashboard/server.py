"""Dashboard backend -- a tiny HTTP server around the gate engine.

The gate itself does not need it: in the real pipeline the agent is a CLI
whose exit code is the decision. The dashboard is the interactive front end
for the same engine: pick or upload a Terraform plan, optionally run a real
`terraform plan` on a seeded module, and get the verdict, the per-layer
trace and downloadable reports.

Deliberately built on the Python standard library only, so it adds zero
dependencies to a project whose whole argument is that the gate must be
cheap and easy to run.

    python -m dashboard.server           # then open http://localhost:8000
    python -m dashboard.server --port 9000 --no-browser
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
PLANS = ROOT / "examples" / "plans"
TF_MODULES = ROOT / "examples" / "terraform"
POLICY = ROOT / "policies" / "policy.yaml"

sys.path.insert(0, str(ROOT))

from agent.config import ReasonerConfig, load_policy  # noqa: E402
from agent.engine import evaluate_plan  # noqa: E402
from agent.plan_parser import PlanParseError, load_plan, parse_plan  # noqa: E402
from agent.report import render_json, render_markdown, render_sarif  # noqa: E402
from agent.rules.base import all_rules  # noqa: E402

# Friendly names for the shipped fixtures, so the dropdown reads like a demo
# script rather than a directory listing.
PLAN_LABELS = {
    "azure_compliant.plan.json": "Azure - compliant workload",
    "azure_noncompliant.plan.json": "Azure - seeded misconfigurations",
    "aws_noncompliant.plan.json": "AWS - seeded misconfigurations",
    "gcp_noncompliant.plan.json": "GCP - seeded misconfigurations",
    "team_demo.plan.json": "Team demo - resourceA (Azure) / B (AWS) / C (GCP)",
    "aws_mesh.plan.json": "AWS - tangled dependency graph (mesh)",
    "aws_thousand_cuts.plan.json": "AWS - six small doors, one database (thousand cuts)",
    "aws_shared_trust.plan.json": "AWS - three teams, one shared key (shared trust)",
    "aws_risk_spectrum.plan.json": "AWS - every risk level in one graph (risk spectrum)",
}

# examples/terraform/<dir> -> what the module is, for the "last local run" group.
MODULE_LABELS = {
    "noncompliant": "Azure - seeded misconfigurations",
    "aws_noncompliant": "AWS - seeded misconfigurations",
    "gcp_noncompliant": "GCP - seeded misconfigurations",
    "aws_mesh": "AWS - tangled dependency graph (mesh)",
    "aws_thousand_cuts": "AWS - six small doors, one database (thousand cuts)",
    "aws_shared_trust": "AWS - three teams, one shared key (shared trust)",
    "aws_risk_spectrum": "AWS - every risk level in one graph (risk spectrum)",
}

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".jsx": "text/babel; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
}

_REASONERS = ("offline", "none", "azure_openai", "anthropic")


def _policy_for(reasoner: str):
    """Load the shipped policy, overriding only the reasoning layer.

    The dashboard's headline demo is toggling Layer 2 on and off and watching
    findings appear and disappear, so this is the one knob it exposes.
    """
    policy = load_policy(str(POLICY))
    if reasoner == "none":
        policy.reasoner = ReasonerConfig(provider="none", enabled=False)
    else:
        policy.reasoner.provider = reasoner
        policy.reasoner.enabled = True
    return policy


def _result_payload(
    plan, reasoner: str, plan_name: str, source: str = "fixture", sha256: str = ""
) -> Dict[str, Any]:
    result = evaluate_plan(plan, _policy_for(reasoner))
    payload = result.to_dict()
    payload["plan_name"] = plan_name
    payload["source"] = source
    payload["plan_sha256"] = sha256
    payload["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # The same renderers the CLI uses, so a downloaded report is exactly what
    # the pipeline would have produced for this plan.
    payload["markdown"] = render_markdown(result)
    payload["report_json"] = render_json(result)
    payload["sarif"] = render_sarif(result)

    per_resource: Dict[str, int] = {}
    for f in result.findings:
        if not f.waived:
            per_resource[f.resource_address] = per_resource.get(f.resource_address, 0) + 1
    payload["resources"] = [
        {
            "address": r.address,
            "type": r.type,
            "cloud": r.provider.value,
            "kind": r.kind.value,
            "action": r.action.value,
            "findings": per_resource.get(r.address, 0),
        }
        for r in plan.mutating
    ]
    return payload


def _plan_catalog() -> Dict[str, Dict[str, Any]]:
    """Every plan the dashboard may evaluate, keyed by a safe opaque name.

    Looking names up here (instead of joining a query parameter onto a path)
    means a request can never read a file outside these directories.
    """
    catalog: Dict[str, Dict[str, Any]] = {}
    for f in sorted(PLANS.glob("*.plan.json")):
        catalog[f.name] = {
            "file": f.name,
            "label": PLAN_LABELS.get(f.name, f.stem),
            "group": "Hand-written fixtures",
            "path": f,
        }
    for f in sorted((PLANS / "real").glob("*.plan.json")):
        key = "real/{}".format(f.name)
        catalog[key] = {
            "file": key,
            "label": "{} (real terraform show -json)".format(PLAN_LABELS.get(f.name, f.stem)),
            "group": "Committed real plan output",
            "path": f,
        }
    if TF_MODULES.is_dir():
        for d in sorted(TF_MODULES.iterdir()):
            if d.is_dir() and (d / "plan.json").is_file():
                key = "terraform/{}".format(d.name)
                catalog[key] = {
                    "file": key,
                    "label": "{} (your last local run)".format(
                        MODULE_LABELS.get(d.name, d.name)),
                    "group": "Generated on this machine by terraform plan -> gate",
                    "path": d / "plan.json",
                }
    return catalog


def _status() -> Dict[str, Any]:
    """Facts about the agent for the "How it works" tab.

    Read-only: counts what is registered and reads the benchmark result last
    written to docs/, so opening the tab never evaluates anything.
    """
    from agent.reasoner.base import load_kb
    from agent.reasoner.offline import _PROBES

    rules = all_rules()
    kb = load_kb()
    recorded: Dict[str, Any] = {}
    bench_file = ROOT / "docs" / "benchmark-results.json"
    if bench_file.is_file():
        try:
            data = json.loads(bench_file.read_text(encoding="utf-8"))
            recorded = {
                "fixtures": data.get("totals", {}),
                "real": (data.get("real") or {}).get("totals", {}),
                "recorded_on": datetime.fromtimestamp(
                    bench_file.stat().st_mtime, timezone.utc
                ).date().isoformat(),
            }
        except (OSError, ValueError):
            recorded = {}
    real_dir = PLANS / "real"
    return {
        "rules": len(rules),
        "caf_rules": sum(1 for r in rules if r.pillar.framework == "CAF"),
        "waf_rules": sum(1 for r in rules if r.pillar.framework == "WAF"),
        "pillars": len({r.pillar for r in rules}),
        "probes": len(_PROBES),
        "kb_pillars": len(kb.get("pillars") or {}),
        "kb_sources": len(kb.get("sources") or []),
        "fixtures": sorted(f.name for f in PLANS.glob("*.plan.json")),
        "real_plans": sorted(f.name for f in real_dir.glob("*.plan.json")) if real_dir.is_dir() else [],
        "seeded_modules": _tf_modules(),
        "benchmark": recorded,
    }


def _find_terraform() -> Optional[str]:
    """Locate the terraform executable.

    A terminal opened before Terraform was installed (or an IDE-launched one)
    often has a stale PATH, so `shutil.which` alone reports "not found" for a
    perfectly good install. Check, in order: SECOPS_TERRAFORM, PATH, then the
    places winget, Chocolatey and the official installer put it.
    """
    explicit = os.environ.get("SECOPS_TERRAFORM")
    if explicit and Path(explicit).is_file():
        return explicit
    found = shutil.which("terraform")
    if found:
        return found
    names = ("terraform.exe", "terraform")
    roots: List[Path] = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        roots += list(Path(local, "Microsoft", "WinGet", "Packages").glob("Hashicorp.Terraform*"))
        roots.append(Path(local, "Microsoft", "WinGet", "Links"))
    for env in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(env)
        if base:
            roots += [Path(base, "Terraform"), Path(base, "HashiCorp", "Terraform")]
    choco = os.environ.get("ChocolateyInstall")
    if choco:
        roots.append(Path(choco, "bin"))
    roots += [Path("/usr/local/bin"), Path("/usr/bin")]
    for root in roots:
        for name in names:
            candidate = root / name
            if candidate.is_file():
                return str(candidate)
    return None


def _tf_modules() -> List[str]:
    """Modules that can be planned from the dashboard.

    Only directories under examples/terraform that hold a main.tf. The
    deployable infra/demo module is deliberately not listed: the dashboard
    never touches live infrastructure.
    """
    if not TF_MODULES.is_dir():
        return []
    return [
        d.name for d in sorted(TF_MODULES.iterdir())
        if d.is_dir() and (d / "main.tf").is_file()
    ]


def _run_step(name: str, cmd: List[str], cwd: Path, timeout: int) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, timeout=timeout,
            env={**os.environ, "TF_IN_AUTOMATION": "1"},
        )
        out = proc.stdout.decode("utf-8", "replace")
        err = proc.stderr.decode("utf-8", "replace")
        ok = proc.returncode == 0
    except subprocess.TimeoutExpired:
        out, err, ok = "", "timed out after {}s".format(timeout), False
    shown = out if ok else (err or out)
    return {
        "name": name,
        "cmd": " ".join(cmd[1:4]),
        "ms": int((time.perf_counter() - started) * 1000),
        "ok": ok,
        "tail": shown.strip().splitlines()[-12:],
        "_stdout": out,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "AgentSecOpsDashboard/2.0"

    # --- plumbing ----------------------------------------------------
    def log_message(self, fmt: str, *args: Any) -> None:
        # One tidy line per request; the default logger is noisy.
        sys.stderr.write("  {} {}\n".format(self.command, self.path))

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: Any, status: int = 200) -> None:
        self._send(
            status,
            json.dumps(payload, indent=2).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _error(self, message: str, status: int = 400) -> None:
        self._json({"error": message}, status)

    # --- routing -----------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        route = urlparse(self.path)
        if route.path.startswith("/api/"):
            return self._api_get(route.path, parse_qs(route.query))
        return self._static(route.path)

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path)
        query = parse_qs(route.query)
        if route.path == "/api/terraform/run":
            return self._terraform_run(query)
        if route.path == "/api/report/pdf":
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0 or length > 8 * 1024 * 1024:
                return self._error("Report body must be between 1 byte and 8 MB.")
            try:
                result = json.loads(self.rfile.read(length).decode("utf-8"))
                from dashboard.pdf import build_report_pdf

                pdf = build_report_pdf(result)
            except (ValueError, KeyError, TypeError) as exc:
                return self._error("Could not build the PDF: {}".format(exc))
            return self._send(200, pdf, "application/pdf")
        if route.path != "/api/evaluate":
            return self._error("Unknown endpoint", 404)

        length = int(self.headers.get("Content-Length", 0))
        if length <= 0 or length > 8 * 1024 * 1024:
            return self._error("Plan body must be between 1 byte and 8 MB.")

        body = self.rfile.read(length)
        try:
            # utf-8-sig: PowerShell's Out-File writes a BOM.
            raw = json.loads(body.decode("utf-8-sig"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return self._error("That is not valid JSON: {}".format(exc))

        reasoner = query.get("reasoner", ["offline"])[0]
        if reasoner not in _REASONERS:
            return self._error("Unknown reasoner: {}".format(reasoner))
        label = (query.get("name", [""])[0] or "uploaded plan")[:120]
        try:
            plan = parse_plan(raw)
        except PlanParseError as exc:
            return self._error(str(exc))
        return self._json(
            _result_payload(
                plan, reasoner, label, "Uploaded or pasted",
                hashlib.sha256(body).hexdigest()[:16],
            )
        )

    def _terraform_run(self, query: Dict[str, list]) -> None:
        """Run the real pipeline: terraform init -> plan -> show -json -> gate."""
        module = query.get("module", [""])[0]
        reasoner = query.get("reasoner", ["offline"])[0]
        if module not in _tf_modules():
            return self._error("Unknown terraform module: {}".format(module), 404)
        if reasoner not in ("offline", "none"):
            return self._error("Unknown reasoner: {}".format(reasoner))
        tf = _find_terraform()
        if not tf:
            return self._error(
                "terraform was not found. Install it (winget install Hashicorp.Terraform), "
                "or set SECOPS_TERRAFORM to the full path of terraform.exe, then restart "
                "the dashboard. The pre-generated plans in the dropdown still work."
            )

        cwd = TF_MODULES / module
        steps: List[Dict[str, Any]] = []
        for name, cmd, timeout in (
            ("terraform init", [tf, "init", "-backend=false", "-input=false", "-no-color"], 300),
            ("terraform plan", [tf, "plan", "-out=tf.plan", "-input=false",
                                "-refresh=false", "-no-color"], 300),
            ("terraform show -json", [tf, "show", "-json", "tf.plan"], 60),
        ):
            step = _run_step(name, cmd, cwd, timeout)
            steps.append(step)
            if not step["ok"]:
                for st in steps:
                    st.pop("_stdout", None)
                return self._json({
                    "error": "{} failed in examples/terraform/{}. See the step log below.".format(
                        name, module),
                    "pipeline": steps,
                }, 422)

        plan_text = steps[-1]["_stdout"]
        (cwd / "plan.json").write_text(plan_text, encoding="utf-8")
        started = time.perf_counter()
        try:
            plan = parse_plan(json.loads(plan_text))
        except (PlanParseError, json.JSONDecodeError) as exc:
            return self._error(str(exc))
        payload = _result_payload(
            plan, reasoner, "terraform/{}".format(module), "Real terraform plan output",
            hashlib.sha256(plan_text.encode("utf-8")).hexdigest()[:16],
        )
        steps.append({
            "name": "agent gate",
            "cmd": "evaluate_plan",
            "ok": True,
            "ms": int((time.perf_counter() - started) * 1000),
            "tail": ["verdict: {}".format(payload["verdict"].upper())],
        })
        for st in steps:
            st.pop("_stdout", None)
        payload["pipeline"] = steps
        return self._json(payload)

    # --- endpoints ---------------------------------------------------
    def _api_get(self, path: str, query: Dict[str, list]) -> None:
        if path == "/api/plans":
            return self._json({
                "plans": [
                    {k: v for k, v in entry.items() if k != "path"}
                    for entry in _plan_catalog().values()
                ],
                "terraform_modules": _tf_modules(),
                "terraform_available": _find_terraform() is not None,
            })

        if path == "/api/rules":
            return self._json({
                "rules": [
                    {
                        "id": r.id,
                        "title": r.title,
                        "pillar": r.pillar.value,
                        "framework": r.pillar.framework,
                        "severity": r.severity.value,
                        "rationale": r.rationale,
                        "remediation": r.remediation,
                        "terraform_fix": r.terraform_fix,
                        "kinds": [k.value for k in r.kinds] or ["all"],
                    }
                    for r in sorted(all_rules(), key=lambda x: x.id)
                ]
            })

        if path == "/api/evaluate":
            name = query.get("plan", [""])[0]
            reasoner = query.get("reasoner", ["offline"])[0]
            if reasoner not in _REASONERS:
                return self._error("Unknown reasoner: {}".format(reasoner))
            entry = _plan_catalog().get(name)
            if not entry:
                return self._error("Unknown plan: {}".format(name), 404)
            try:
                plan = load_plan(str(entry["path"]))
            except PlanParseError as exc:
                return self._error(str(exc))
            digest = hashlib.sha256(entry["path"].read_bytes()).hexdigest()[:16]
            return self._json(_result_payload(plan, reasoner, name, entry["group"], digest))

        if path == "/api/status":
            return self._json(_status())

        if path == "/api/benchmark":
            from scripts.benchmark import evaluate as run_benchmark

            return self._json(run_benchmark())

        return self._error("Unknown endpoint", 404)

    # --- static files ------------------------------------------------
    def _static(self, path: str) -> None:
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        target = (STATIC / rel).resolve()
        if STATIC not in target.parents and target != STATIC:
            return self._error("Forbidden", 403)
        if not target.is_file():
            return self._error("Not found", 404)
        content_type = _CONTENT_TYPES.get(target.suffix, "application/octet-stream")
        self._send(200, target.read_bytes(), content_type)


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent SecOps dashboard.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    url = "http://{}:{}".format(
        "localhost" if args.host in ("127.0.0.1", "0.0.0.0") else args.host, args.port
    )

    try:
        server = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as exc:
        print("Could not start on port {}: {}".format(args.port, exc))
        print("Another program is probably using it. Try: --port 8001")
        return 1

    print("")
    print("  Agent SecOps dashboard")
    print("  " + "-" * 46)
    print("  Open:  {}".format(url))
    print("  Stop:  Ctrl+C")
    print("")

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
