#!/usr/bin/env bash
###############################################################################
# Local demo -- the five-minute version of the project, no cloud required.
#
# Runs the gate against every fixture and shows the pass/block decision that
# a GitHub Actions run would make. Costs nothing: no Azure API is touched.
###############################################################################
set -uo pipefail
cd "$(dirname "$0")/.."

banner() { printf '\n\033[1m=== %s ===\033[0m\n' "$1"; }

banner "1. The rule catalogue"
python -m agent.cli rules

banner "2. Compliant Azure workload (expected: PASS, exit 0)"
python -m agent.cli evaluate --plan examples/plans/azure_compliant.plan.json
echo "exit=$?"

banner "3. Seeded misconfigurations (expected: BLOCK, exit 2)"
python -m agent.cli evaluate --plan examples/plans/azure_noncompliant.plan.json
echo "exit=$?"

banner "4. Same gate, AWS plan (cloud-agnostic proof)"
python -m agent.cli evaluate --plan examples/plans/aws_noncompliant.plan.json
echo "exit=$?"

banner "5. Same gate, GCP plan"
python -m agent.cli evaluate --plan examples/plans/gcp_noncompliant.plan.json
echo "exit=$?"

banner "6. Why one rule exists (framework traceability)"
python -m agent.cli explain WAF-SEC-004

banner "7. The PR report a developer actually sees"
python -m agent.cli evaluate \
  --plan examples/plans/azure_noncompliant.plan.json \
  --markdown out/gate-report.md >/dev/null
head -40 out/gate-report.md

banner "8. Detection benchmark"
python scripts/benchmark.py | head -20

printf '\n\033[1mDemo complete. Nothing was deployed and no cloud credits were used.\033[0m\n'
