# Team Split — Contribution Breakdown

Project ID 19727UG01 · Agent SecOps · Guide: Dr. SM Farooq

Weighted by scope and complexity, not by file count alone:

| Weight | Owner | Area | What it covers |
|---|---|---|---|
| **Major** | **Gaurish Todi** | AI reasoning engine, orchestration, evaluation, dashboard | The core intelligence of the project and how its results are measured and shown |
| **Medium** | **Akshat Gupta** | Plan parsing + deterministic rule engine | Turning a Terraform plan into 22 concrete CAF/WAF checks |
| **Light** | **Bhumika Singh** | CI/CD pipeline, Terraform infra, Azure setup, CLI/reporting | Wiring the engine into a real pipeline and a real (cheap) Azure deployment |

---

# Gaurish Todi — Major Contribution
## The AI Reasoning Engine, Orchestration, Evaluation & Dashboard

This is the intellectual core of the project: the part that goes beyond "check a list of rules" into "reason about guidance that was never written as a rule," plus the machinery that turns that reasoning into a verdict, measures how well it works, and shows it on screen.

### Files and folders owned

| Path | What it is |
|---|---|
| `agent/engine.py` | The orchestrator — runs Layer 1 (rules) → Layer 2 (reasoning) → Layer 3 (policy), produces the final verdict |
| `agent/config.py` | The policy engine — thresholds, rule overrides, time-boxed waivers |
| `agent/reasoner/base.py` | Shared retrieval logic: pulls only the relevant CAF/WAF guidance for a resource |
| `agent/reasoner/offline.py` | The free, deterministic reasoning layer — 12 heuristic probes, the CI default |
| `agent/reasoner/llm.py` | The paid LLM reasoning layer (Azure OpenAI / Anthropic), with cost caps and caching |
| `agent/reasoner/__init__.py` | Reasoner selection with automatic fallback if no LLM is configured |
| `agent/knowledge/caf_waf_kb.yaml` | The knowledge base — CAF/WAF pillar guidance in prose, indexed by resource kind |
| `dashboard/server.py` | Python backend serving the demo dashboard, wrapping the engine in an HTTP API |
| `dashboard/static/app.jsx` | The React frontend — verdict banner, charts, findings, benchmark view |
| `dashboard/static/index.html`, `styles.css` | Dashboard page shell and the validated colour system |
| `scripts/benchmark.py` | The evaluation harness — 42 labelled violations, measures detection rate and false positives |
| `tests/test_engine.py` | 18 end-to-end tests: verdicts, waivers, both layers, all three report formats |
| `docs/architecture.md` | The full technical design document and its rationale |
| `docs/dashboard.md`, `docs/benchmark-results.md` | Dashboard usage guide and the measured results |

### What to say

> "My part answers the question the whole project exists to answer: can an AI agent catch CAF/WAF violations that a static rule never could? The engine in `agent/engine.py` runs three layers — deterministic rules first, because they're free and certain; then my reasoning layer, which retrieves only the framework guidance relevant to a resource from a knowledge base I wrote in `agent/knowledge/caf_waf_kb.yaml`, and looks for violations no rule encodes; then policy, which applies an organisation's thresholds and any time-boxed waivers.
>
> The reasoning layer has two interchangeable implementations. The offline one is free heuristics — it's also the control arm of an experiment: I run the same plan with and without it and measure the difference. The LLM one calls a real model but is capped on resource count, output tokens, and cached, so a repeat run costs nothing.
>
> `scripts/benchmark.py` is how I prove the claim rather than assert it: 42 hand-labelled violations across three clouds. Rules alone catch 88%. With reasoning, 100%. Five violations are recoverable only by reasoning — that's the actual contribution, quantified.
>
> The dashboard is the same engine wired to a browser so the result is visible, not just a terminal exit code."

### Depth points if asked

- **Why the reasoning layer can't block a build by default** (`fail_on_reasoner_findings: false` in `agent/config.py`): an LLM is non-deterministic and sits on a control path, so it's advisory until an org measures its precision and opts in.
- **Why retrieval is keyed on resource kind, not embeddings**: it's cheaper and fully deterministic — you can say in advance exactly what guidance any resource will be judged against.
- **Why waivers expire** (`Waiver.is_expired()` in `config.py`): every compliance exception process dies the same way — "temporary" becomes permanent. An expired waiver stops suppressing its finding and is called out in the report.

---

# Akshat Gupta — Medium Contribution
## Plan Parsing and the Deterministic Rule Engine

This is Layer 1: turning a raw Terraform plan into something checkable, and the 22 concrete rules that check it.

### Files and folders owned

| Path | What it is |
|---|---|
| `agent/models.py` | The data model — `Resource`, `Finding`, `Pillar`, `Severity`, `Verdict` |
| `agent/plan_parser.py` | Terraform plan JSON → normalized, cloud-agnostic `Resource` objects |
| `agent/rules/base.py` | The `Rule` base class and the registry every rule plugs into |
| `agent/rules/caf.py` | 7 CAF rules — governance tags, naming, landing-zone region, network boundary, cost attribution, identity |
| `agent/rules/waf.py` | 15 WAF rules — security, reliability, cost, operations, performance, sustainability |
| `tests/test_plan_parser.py` | Parser tests — provider detection, the firewall/database misclassification fix |
| `tests/test_rules.py` | Every rule tested in both directions: fires on the violation, silent on the compliant case |

### What to say

> "My module is what makes the gate cloud-agnostic. Terraform emits a `resource_changes` list — for each resource, its type and its full planned configuration. I parse that in `plan_parser.py` and, critically, map every provider-specific type to one canonical `Kind`: `azurerm_storage_account`, `aws_s3_bucket`, and `google_storage_bucket` all become `Kind.OBJECT_STORAGE`. That's the whole multi-cloud story — a rule written once against `OBJECT_STORAGE` works on all three clouds.
>
> Then 22 rules in `agent/rules/` run against those resources. Each one is a small class: an id, a mandatory CAF or WAF pillar, a severity, and a `check()` method. The pillar is enforced by the type system — a finding literally cannot exist without naming which pillar it violates."

### Depth points if asked

- **The firewall/database bug** (now a regression test): `azurerm_mssql_firewall_rule` contains the substring "sql", so the fallback classifier put it in the database bucket, producing three false positives (missing tags, missing cost centre, missing diagnostics) on an object that has none of those. Fixed by matching firewall patterns before database patterns.
- **`["delete","create"]` is a replacement, not a delete**: Terraform's plan JSON encodes a forced replacement as both actions in one list. Treating it as a delete would let every create-time rule skip a resource being force-replaced.
- **Unknown types fall to heuristics, not silence**: an unrecognised resource type is substring-matched into the closest bucket rather than dropped, so the gate never develops a blind spot on a new resource type.

---

# Bhumika Singh — Light Contribution
## CI/CD Pipeline, Terraform Infrastructure, Azure Setup & CLI/Reporting

This is the connective tissue: wiring the engine into a real GitHub Actions pipeline, a real (cheap) Terraform deployment, and the command-line surface the pipeline actually runs.

### Files and folders owned

| Path | What it is |
|---|---|
| `.github/workflows/secops-gate.yml` | The pipeline: tests → plan both modules → gate → PR comment → apply behind approval |
| `infra/demo/` | The compliant demo module (`main.tf`, `variables.tf`, `outputs.tf`, `terraform.tfvars.example`) |
| `examples/terraform/noncompliant/main.tf` | The seeded misconfiguration module used as the gate's own regression test |
| `examples/plans/*.plan.json` | The four plan fixtures (Azure ×2, AWS, GCP) used by tests and the benchmark |
| `scripts/azure-bootstrap.sh` | One-time Azure setup: resource groups, state storage, OIDC federation, budget alert |
| `scripts/azure-cost-check.sh`, `azure-destroy.sh` | Credit guardrails — what's running, and tearing it back down |
| `scripts/demo.sh` | The no-cloud local demo walkthrough |
| `agent/report.py` | Markdown / JSON / SARIF report renderers |
| `agent/cli.py` | The CLI the pipeline actually invokes, and its exit-code contract |
| `policies/policy.yaml` | The organisation-tunable policy file |
| `docs/azure-setup.md`, `docs/cost-control.md`, `docs/setup-from-zero.md` | Setup, cost, and from-zero walkthroughs |

### What to say

> "My part makes this an actual pipeline gate instead of a script someone runs by hand. The workflow in `.github/workflows/secops-gate.yml` runs the agent's own tests first, then plans two Terraform modules in parallel — the compliant one, which must pass, and a seeded misconfiguration module, which must be blocked. If the seeded module is ever *not* blocked, the build fails — that's a regression test for the gate itself, running on every change.
>
> The Terraform module in `infra/demo/` is deliberately minimal — a resource group, a storage account, and a free-tier Log Analytics workspace with a hard daily quota, nothing that costs real money. Authentication uses GitHub OIDC federation, so no client secret is ever stored in the repo.
>
> `agent/cli.py` is the actual command the pipeline runs, and its exit code — 0, 1, or 2 — is the entire integration surface. `agent/report.py` turns a verdict into a PR comment, a JSON artifact, and a SARIF file for GitHub's Security tab."

### Depth points if asked

- **Why OIDC instead of a stored secret**: GitHub presents a signed token, Azure exchanges it for one valid for minutes — nothing long-lived is ever stored, which is exactly the pattern the project's own `WAF-SEC-006` rule flags when done wrong.
- **Why least-privilege scoping matters here**: the service principal is granted Contributor on two resource groups, not the subscription — because the project's own `CAF-IAM-001` rule would flag a subscription-wide grant as critical.
- **Why `--soft-fail` exists** (`agent/cli.py`): onboarding an existing repo with pre-existing violations needs a report-only mode first; a gate that can't be adopted incrementally doesn't get adopted.

---

# Presentation running order

| Slot | Who | Content | Time |
|---|---|---|---|
| 1 | **Gaurish** | Problem, architecture, the reasoning layer, dashboard demo | 5 min |
| 2 | **Akshat** | Plan parsing, canonical kinds, the rule catalogue | 3 min |
| 3 | **Bhumika** | Pipeline, Azure setup, CLI and reports | 3 min |
| 4 | **Gaurish** | Benchmark results, limitations, next steps | 3 min |
| — | All | Questions | — |

---

# Integration checklist

```bash
python -m pytest tests/ -q          # 63 passed
python scripts/benchmark.py         # 100% detection, 0 false positives
python -m dashboard.server          # dashboard loads, all 3 tabs work
bash scripts/demo.sh                # full local walkthrough, no cloud needed
```
