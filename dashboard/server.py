"""Dashboard backend -- a tiny HTTP server around the gate engine.

This exists purely to make the project demonstrable in a browser. The gate
itself does not need it: in the real pipeline the agent is a CLI whose exit
code is the decision. The dashboard is the presentation layer for a viva.

Deliberately built on the Python standard library only, so it adds zero
dependencies to a project whose whole argument is that the gate must be
cheap and easy to run.

    python -m dashboard.server           # then open http://localhost:8000
    python -m dashboard.server --port 9000 --no-browser
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
PLANS = ROOT / "examples" / "plans"
POLICY = ROOT / "policies" / "policy.yaml"

sys.path.insert(0, str(ROOT))

from agent.config import ReasonerConfig, load_policy  # noqa: E402
from agent.engine import evaluate_plan  # noqa: E402
from agent.plan_parser import PlanParseError, load_plan, parse_plan  # noqa: E402
from agent.report import render_markdown  # noqa: E402
from agent.rules.base import all_rules  # noqa: E402

# Friendly names for the shipped fixtures, so the dropdown reads like a demo
# script rather than a directory listing.
PLAN_LABELS = {
    "azure_compliant.plan.json": "Azure - compliant workload",
    "azure_noncompliant.plan.json": "Azure - seeded misconfigurations",
    "aws_noncompliant.plan.json": "AWS - seeded misconfigurations",
    "gcp_noncompliant.plan.json": "GCP - seeded misconfigurations",
}

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".jsx": "text/babel; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
}


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


def _result_payload(plan, reasoner: str, plan_name: str) -> Dict[str, Any]:
    result = evaluate_plan(plan, _policy_for(reasoner))
    payload = result.to_dict()
    payload["plan_name"] = plan_name
    payload["markdown"] = render_markdown(result)
    payload["resources"] = [
        {
            "address": r.address,
            "type": r.type,
            "cloud": r.provider.value,
            "kind": r.kind.value,
            "action": r.action.value,
        }
        for r in plan.mutating
    ]
    return payload


class Handler(BaseHTTPRequestHandler):
    server_version = "AgentSecOpsDashboard/1.0"

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
        path = route.path
        query = parse_qs(route.query)

        if path.startswith("/api/"):
            return self._api_get(path, query)
        return self._static(path)

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path)
        if route.path != "/api/evaluate":
            return self._error("Unknown endpoint", 404)

        length = int(self.headers.get("Content-Length", 0))
        if length <= 0 or length > 8 * 1024 * 1024:
            return self._error("Plan body must be between 1 byte and 8 MB.")

        try:
            raw = json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return self._error("Uploaded file is not valid JSON: {}".format(exc))

        reasoner = parse_qs(urlparse(self.path).query).get("reasoner", ["offline"])[0]
        try:
            plan = parse_plan(raw)
        except PlanParseError as exc:
            return self._error(str(exc))
        return self._json(_result_payload(plan, reasoner, "uploaded plan"))

    # --- endpoints ---------------------------------------------------
    def _api_get(self, path: str, query: Dict[str, list]) -> None:
        if path == "/api/plans":
            plans = []
            for f in sorted(PLANS.glob("*.plan.json")):
                plans.append({
                    "file": f.name,
                    "label": PLAN_LABELS.get(f.name, f.stem),
                })
            return self._json({"plans": plans})

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
            if reasoner not in ("offline", "none", "azure_openai", "anthropic"):
                return self._error("Unknown reasoner: {}".format(reasoner))

            target = PLANS / name
            # Never let a query parameter escape the fixtures directory.
            if not name or target.parent != PLANS or not target.exists():
                return self._error("Unknown plan: {}".format(name), 404)
            try:
                plan = load_plan(str(target))
            except PlanParseError as exc:
                return self._error(str(exc))
            return self._json(_result_payload(plan, reasoner, name))

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
