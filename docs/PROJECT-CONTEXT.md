# Agent SecOps — Master Context Document

**Purpose of this file.** A single, self-contained reference to the entire project — what it is, how it works, what has actually been built, deployed, tested and documented, and what remains open. Written so that a new session, a new collaborator, or a future you can pick this up cold and be fully oriented in one read. Everything here reflects verified state as of the date below, not aspiration.

**Last verified:** 2026-10-02 · **Repo:** [github.com/GAURISHTODI/Agent-SecOps](https://github.com/GAURISHTODI/Agent-SecOps) · **Tests:** 63/63 passing · **Live Azure:** 3 resources deployed and gated, zero config drift

> **2026-10-02 update.** A second working session (three weeks after the first) found and fixed four real bugs that only surfaced from actually running things again: a broken local dev environment (missing PyYAML), a genuine `terraform validate` failure in CI (the seeded module had an empty `network_interface_ids` list, which the AzureRM schema rejects), live Azure config drift from an AzureRM provider deprecation (`metric` → `enabled_metric`), and a missing `.gitignore` pattern for Office lock files. A budget alert that the CLI had refused to create was created successfully via a direct REST call. All of this is committed and pushed (`6383d04`). See §13 for the full account. The CI pipeline's remaining failure is now isolated to one cause: the three `AZURE_CLIENT_ID`/`AZURE_TENANT_ID`/`AZURE_SUBSCRIPTION_ID` GitHub secrets, which cannot be read back to diagnose and must be reset by a human with repo admin access — everything else about the Azure-side identity (app registration, federated credentials, role assignments) was independently verified correct.

---

## 1. What this project is

### 1.1 In one sentence

An AI agent sits between `terraform plan` and `terraform apply` in a GitHub Actions pipeline, reads the plan JSON, judges every proposed cloud resource against Microsoft's Cloud Adoption Framework (CAF) and Well-Architected Framework (WAF), and returns **pass / remediate / block** with a plain-language report — so a non-compliant resource is stopped before it exists and before it costs anything.

### 1.2 The problem it solves (plain language)

Cloud teams describe infrastructure in a "recipe file" (Terraform) and a pipeline cooks it (deploys it) automatically. Before the recipe is executed there is one moment where the full list of what's about to be built is known but nothing has been created yet. This project puts an AI security guard at exactly that moment.

The guard checks the recipe against two Microsoft rulebooks:
- **CAF** — is this being set up responsibly? (tagged, right region, cost-tracked, least-privilege identity)
- **WAF** — is this actually built well? (encrypted, backed up, not wide open to the internet)

If the recipe breaks the rules, the guard blocks it before it's ever created. No wasted money, no security hole ever exists.

### 1.3 Why this isn't "just another Checkov"

Static policy-as-code tools (Checkov, tfsec, OPA, Sentinel) only catch violations of rules **someone already wrote**. CAF and WAF are thousands of words of narrative architectural guidance that were never turned into rules. This project adds a **reasoning layer** on top of deterministic rules that retrieves the relevant framework guidance for a resource and judges it for violations no rule encodes — the way an experienced human reviewer would.

### 1.4 Academic framing

- **Project ID:** 19727UG01
- **Course:** BCSE497J — Project-I (B.Tech Computer Science and Engineering)
- **Faculty guide:** Dr. S. M. Farooq
- **SDG alignment:** SDG 9 (Industry, Innovation and Infrastructure), Target 9.5
- **TRL:** Advanced from TRL 3 (Review-1: analytical proof of concept, no prototype) to **TRL 4** (this build: component validation in a lab environment, validated against live Azure)

---

## 2. Team and division of work

Sorted by register number where the template requires it; by contribution weight elsewhere.

| Reg. No. | Name | Weight | Module |
|---|---|---|---|
| 23BCE0196 | **Bhumika Singh** | Light | CI/CD pipeline, Terraform infrastructure, Azure provisioning, CLI and report rendering |
| 23BCE0958 | **Akshat Gupta** | Medium | Plan parsing, canonical resource model, deterministic CAF/WAF rule engine |
| 23BCI0262 | **Gaurish Todi** | Major | Knowledge base, reasoning layer, orchestration engine, policy engine, evaluation harness, dashboard |

### 2.1 Gaurish Todi (23BCI0262) — Major

**Owns:** `agent/engine.py`, `agent/config.py`, `agent/reasoner/` (base.py, offline.py, llm.py), `agent/knowledge/caf_waf_kb.yaml`, `dashboard/`, `scripts/benchmark.py`, `tests/test_engine.py`, `docs/architecture.md`

**Did:** Designed the three-layer architecture; authored the CAF/WAF knowledge base and the retrieval-based reasoning layer; implemented verdict orchestration, severity thresholds and expiring waivers; built the evaluation harness measuring detection rate, false positives and the marginal contribution of reasoning; built the demonstration dashboard (React frontend + Python backend).

### 2.2 Akshat Gupta (23BCE0958) — Medium

**Owns:** `agent/models.py`, `agent/plan_parser.py`, `agent/rules/` (base.py, caf.py, waf.py), `tests/test_plan_parser.py`, `tests/test_rules.py`

**Did:** Defined the cloud-agnostic data model; implemented Terraform plan JSON parsing and the canonical-kind mapping that makes the gate multi-cloud; authored all 22 deterministic CAF and WAF rules with framework rationale; wrote bidirectional rule tests (fires on the violation, silent on the compliant case).

### 2.3 Bhumika Singh (23BCE0196) — Light

**Owns:** `.github/workflows/secops-gate.yml`, `infra/demo/`, `examples/terraform/noncompliant/`, `examples/plans/`, `scripts/azure-*.sh`, `agent/report.py`, `agent/cli.py`, `policies/policy.yaml`, `docs/azure-setup.md`

**Did:** Built the GitHub Actions workflow positioning the gate between plan and apply; authored the compliant Terraform module and the seeded misconfiguration module; configured Azure OIDC federation and least-privilege access; implemented the CLI exit-code contract and the Markdown/JSON/SARIF renderers.

---

## 3. Architecture

### 3.1 Where the agent sits

```
Developer commits .tf
        |
GitHub Actions triggered
        |
terraform plan -out=tf.plan
terraform show -json tf.plan  ->  plan.json
        |
┌───────────────────────────────────────────────┐
│              AGENT SECOPS GATE                 │
│  plan_parser -> normalized Resource objects    │
│       |                                        │
│       +-> Layer 1: deterministic CAF/WAF rules │
│       |            (22 rules, confidence 1.0)  │
│       +-> Layer 2: framework reasoning         │
│       |            (what no rule encodes)      │
│       +-> Layer 3: org policy                  │
│                    thresholds + waivers        │
│                          |                     │
│                     verdict + report           │
└──────────────────────────┬──────────────────────┘
         BLOCK <───────────┴───────────> PASS
           |                              |
   report on PR, exit 2           terraform apply, exit 0
   nothing deployed                -> Azure / AWS / GCP
```

**Why here specifically:** the plan JSON is the earliest point at which the fully resolved set of changes is known (variables, modules, `count`/`for_each` already evaluated), and the last point before anything is created. Three alternatives were considered and rejected: gating raw `.tf` source (variables unresolved, so you can't see what's actually going to be built), gating after `apply` via Azure Policy/Defender (money already spent, exposure may have already happened), and manual review (doesn't scale to dozens of PRs/day across three clouds).

### 3.2 The four layers

**Layer 0 — Normalization** (`agent/plan_parser.py`). Terraform's `resource_changes[]` array is parsed into `Resource` objects carrying a **canonical `Kind`**. `azurerm_storage_account`, `aws_s3_bucket`, `google_storage_bucket` all become `Kind.OBJECT_STORAGE`. This one mapping table is the entire multi-cloud story — one rule written against a canonical kind works on all three clouds. `["delete","create"]` in the actions list is recognized as a forced replacement (not a delete) so create-time rules still run against it. Unknown resource types fall through to substring heuristics rather than being silently skipped.

**Layer 1 — Deterministic rules** (`agent/rules/`). 22 rules, each a small class declaring an id, a mandatory `Pillar` (CAF or WAF — enforced by the type system, a finding cannot exist without naming its pillar), a severity, applicable kinds, a `check()` method, and a `rationale` string (the framework justification, tested to exist on every rule). Confidence is always 1.0. Rule parameters (approved regions, mandatory tags, sensitive ports) are overridable from `policies/policy.yaml` without touching Python.

Coverage: CAF Governance (2 rules), CAF Landing Zone (3), CAF Cost Management (1), CAF Identity (1), WAF Security (6), WAF Reliability (3), WAF Cost Optimization (2), WAF Operational Excellence (2), WAF Performance Efficiency (1), WAF Sustainability (1).

**Layer 2 — Reasoning** (`agent/reasoner/`). The knowledge base (`agent/knowledge/caf_waf_kb.yaml`) holds CAF/WAF guidance in prose plus a `kind_focus` retrieval index mapping each canonical resource kind to the pillars and specific watch-points worth considering. Retrieval is keyed on the type system, not embedding similarity — deterministic and auditable. Two interchangeable reasoners:
- `OfflineReasoner` — 12 free, deterministic heuristic probes; the CI default; also the experimental control arm (the offline reasoner is what recall-without-an-LLM looks like, so the marginal value of the paid path is measurable).
- `LLMReasoner` — talks to Azure OpenAI or Anthropic over plain `urllib` (no vendor SDK). Cost-capped: max resources per run, max output tokens, prompt redaction/truncation, disk cache keyed on model+prompt hash. Falls back silently to the offline reasoner if no endpoint is configured or the endpoint is unreachable — the gate never breaks because a model is down.

Four guardrails make the reasoning layer safe on a control path: it cannot invent resources (findings referencing an address not in the submitted set are dropped), cannot duplicate Layer 1 (receives `already_reported` titles and is instructed not to repeat them — tested), cannot block a build by default (`fail_on_reasoner_findings: false` — advisory only until an org opts in after measuring precision), and cannot break the pipeline (endpoint failure degrades to an informational finding, not a crash).

**Layer 3 — Policy** (`agent/config.py`). Severity thresholds (`block_at`, `remediate_at`), rule enable/disable and parameter overrides, and **time-boxed waivers**. A waiver requires a `reason`, matches by glob, and **expires** — an expired waiver stops suppressing its finding and is called out in the report, so "temporary" exceptions can't quietly become permanent.

### 3.3 Output (`agent/report.py`)

Three formats from one `GateResult`: **Markdown** (PR comment, updated in place across pushes rather than spamming new comments — verdict banner, per-pillar table, findings grouped by resource with copy-pasteable HCL fixes), **JSON** (machine-readable, consumed by the benchmark harness and the dashboard), **SARIF 2.1.0** (GitHub Security tab, tracked alerts).

### 3.4 CLI contract (`agent/cli.py`)

Exit code is the entire pipeline integration surface:

| Code | Verdict | Pipeline behaviour |
|---|---|---|
| 0 | `pass` | `terraform apply` proceeds |
| 1 | `remediate` | Warn; proceeds only with `--soft-fail` |
| 2 | `block` | Pipeline stops, nothing deployed |
| 3 | error | Bad plan file or usage |

`--soft-fail` exists for incremental adoption: report-only mode for onboarding a repo with an existing violation backlog.

---

## 4. Repository layout

```
agent/                     the gate itself
  models.py                cloud-agnostic data model (Resource, Finding, Pillar, Severity, Verdict)
  plan_parser.py            Terraform plan JSON -> normalized resources
  rules/
    base.py                rule base class + registry
    caf.py                 7 CAF rules
    waf.py                 15 WAF rules
  reasoner/
    base.py                retrieval + redaction, shared by both reasoners
    offline.py              free deterministic heuristics (CI default)
    llm.py                  Azure OpenAI / Anthropic, cost-capped + cached
  knowledge/caf_waf_kb.yaml the framework guidance the reasoner reads
  engine.py                 orchestration: rules -> reasoning -> policy -> verdict
  report.py                  Markdown / JSON / SARIF renderers
  cli.py                     the command the pipeline runs
  config.py                  thresholds, rule overrides, time-boxed waivers

dashboard/                 local demo UI (not part of the gate)
  server.py                 stdlib HTTP backend around the engine
  static/                    React frontend (index.html, app.jsx, styles.css)

policies/policy.yaml        the only file a platform team needs to edit
infra/demo/                minimal compliant Azure module (deployed, live)
examples/terraform/noncompliant/   seeded misconfiguration module (plan-only)
examples/plans/             4 plan fixtures: Azure x2, AWS, GCP
.github/workflows/secops-gate.yml  the pipeline
scripts/
  azure-bootstrap.sh, azure-cost-check.sh, azure-destroy.sh
  benchmark.py               evaluation harness
  demo.sh                    local demo walkthrough
  build_report.py, build_ppt.py, build_figures.py   document generators (new)
docs/                       all documentation (see §9)
tests/                       63 tests
```

---

## 5. What is actually built and verified (not aspirational)

- **63 automated tests, all passing.** Parser (provider detection, canonical-kind mapping across 3 clouds, the firewall/database misclassification regression, replace-as-create), rules (every rule tested both directions — fires on violation, silent on compliant), engine (verdicts, waiver expiry, threshold changes, both layers contributing, no duplication between layers, all 3 report formats, CLI exit codes, malformed-plan resilience).
- **Benchmark: 42 hand-labelled seeded violations across Azure/AWS/GCP.** Rules alone: 37/42 (88.1%). Rules + reasoning: 42/42 (100%). **5 violations recoverable only by reasoning** — the quantified research claim. **0 false positives** on the compliant module. Median latency < 10 ms. Reproduce: `python scripts/benchmark.py`.
- **Local dashboard** (`python -m dashboard.server`) — 3 tabs (Gate, Benchmark, Rules), reasoning-layer on/off toggle, plan upload, all driven by the same engine as the CLI.
- **GitHub repository live and pushed:** [github.com/GAURISHTODI/Agent-SecOps](https://github.com/GAURISHTODI/Agent-SecOps), 2 commits, scanned clean for secrets before every push.
- **Real Azure deployment**, not just fixtures (see §6).
- **Full Project-I report and Review-2 PPT generated**, filled, diagrammed (see §7).

---

## 6. Azure deployment — real, live, verified

### 6.1 Account

- **Login:** `gaurishtodi@gmail.com`
- **Subscription:** Visual Studio Enterprise Subscription (`f2c8dcf2-da4a-43ae-9b8d-51ada86f4c15`)
- **Tenant:** `da8d0e2e-bbb4-416a-a0c4-aef68e06c869`
- Note: this is a *different* subscription from an earlier VIT-student login (`gaurish.todi2023@vitstudent.ac.in`, "Azure for Students") seen briefly during setup — the student subscription's credits are **not** what's backing this deployment. VS Enterprise carries its own monthly Azure credit allowance.

### 6.2 What is currently live (verified by direct `az resource list`, independent of any client-side tool state)

| Resource | Resource group | Config | Cost |
|---|---|---|---|
| `secops-tfstate-rg` | — | Terraform state backend RG | Free |
| `secopstfstate4853` | secops-tfstate-rg | Storage account, Standard_LRS, versioned | ~₹2/mo |
| `secops-dev-cin-rg` | — | Workload RG, Central India, fully tagged | Free |
| `secopsdevcindata` | secops-dev-cin-rg | Storage account, Standard_LRS, TLS1.2, HTTPS-only, **public access Disabled**, no shared keys | ~₹2/mo |
| `secops-dev-cin-law` | secops-dev-cin-rg | Log Analytics, PerGB2018, **0.1 GB/day hard cap**, 30-day retention | ₹0 (free tier) |
| `secops-dev-cin-storage-diag` | secops-dev-cin-rg | Diagnostic setting (extension resource, not in `az resource list`, confirmed via `terraform state show`) | Free |

**Total steady-state cost: ~₹4/month.**

**Identity for CI/CD:** app registration `secops-github-oidc` (client ID `01548123-a938-4fd1-89b3-979a8bb6cab3`) with 3 federated credentials (`gh-main` for branch main, `gh-pr` for pull_request, `gh-env-production` for the production environment) — **no client secret ever created or stored**. Contributor role granted on the two resource groups only, not the subscription (subscription-scope would trip our own `CAF-IAM-001` rule). Data-plane roles `Storage Blob/Queue Data Contributor` also granted to both the CI service principal and the interactive user, needed because `shared_access_key_enabled = false` forces Azure AD-based reads.

### 6.3 The real end-to-end run that was executed

```
terraform plan (against live Azure)  ->  plan.json (real, not a fixture)
       |
python -m agent.cli evaluate --plan infra/demo/plan.json
       |
PASS, 1 finding (LOW: infrastructure_encryption_enabled false), exit 0
       |
terraform apply  ->  4 resources created in Azure
       |
re-plan  ->  no drift; re-gate  ->  PASS, 0 findings, exit 0
```

This proves the actual claim of the project on real infrastructure, not a fixture: **plan → gate → apply**, in that order, with the gate genuinely holding up `apply` until it returns 0.

### 6.4 GitHub secrets/variables configured (values are identifiers, not credentials)

Repository secrets: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`. Repository variables: `TFSTATE_RG=secops-tfstate-rg`, `TFSTATE_SA=secopstfstate4853`. Protected environment `production` created with required-reviewer approval.

### 6.5 Three real bugs found and fixed by doing this for real

These only surfaced because the gate was run against genuinely live Azure rather than only fixtures — each is fixed, tested, committed (`git log`: `306e01d`):

1. **UTF-8 BOM rejection.** PowerShell's `Out-File -Encoding utf8` always writes a BOM. `plan_parser.py` used strict `utf-8` decoding, so every `plan.json` produced the documented Windows way was rejected. Fixed: `utf-8-sig`.
2. **403 on storage account refresh.** `shared_access_key_enabled = false` (our own WAF-SEC rule, correctly applied) broke the AzureRM provider's default key-based read of queue properties. Fixed: `storage_use_azuread = true` on the provider block, plus the data-plane RBAC grants in §6.2.
3. **Broken `.gitignore` patterns.** Git has no inline-comment syntax; `terraform.tfvars  # comment` and `.secops_cache/  # comment` never matched anything, because the whole line including the comment was treated as the pattern. This meant `terraform.tfvars` — which holds subscription-specific values — was not actually being ignored. Fixed: comments moved to their own line above each pattern.

### 6.6 Known environment friction encountered (informational, not project defects)

- The development network exhibited intermittent to (briefly) persistent TCP resets on IPv6 routes to `management.azure.com` — affected `az`, Terraform's provider registry, and Terraform's backend calls equally, confirming it was network-level, not tool-specific. Mitigated by retrying; user declined the offered fix (deprioritizing IPv6 via `Disable-NetAdapterBinding`) in favor of persistence, which worked.
- The `C:` drive briefly hit 0 bytes free mid-session, which corrupted Azure CLI's local token cache (`msal_token_cache.bin`, truncated to 0 bytes) and its telemetry writer. Fixed by clearing the corrupted cache and disabling `az` telemetry (`az config set core.collect_telemetry=false`) so it can't recur. User freed disk space; current free space ~2.6 GB on C:.

### 6.7 Outstanding manual step

**Budget alert.** The `az consumption budget create` API rejects requests on this subscription type (`400 Invalid budget configuration`, preview API limitation on Visual Studio Enterprise subscriptions). Not yet set. **Action required:** Portal → Cost Management + Billing → Budgets → Add → ₹500/month → alerts at 50/80/100%.

---

## 7. Documents generated

Two deliverables were generated by filling the supplied VIT templates programmatically (`scripts/build_report.py`, `scripts/build_ppt.py`), with 8 diagrams drawn programmatically (`scripts/build_figures.py`, output in `docs/figures/`) and embedded — no placeholder boxes left in either file.

### 7.1 `Agent SecOps - BCSE497J Project-I Report.docx`

Follows the template's exact structure, fonts (Times New Roman, prescribed sizes/weights per heading level) and word limits (Abstract 282/300, Background 191/200, Motivation 183/200, Scope 166/200). 9 embedded images (VIT logo + 8 figures), 8 tables (including the two contribution tables from §2), ~4,700 words. Literature review cites 16 real papers (Rahman et al. ICSE'19 on IaC security smells, GLITCH ASE'22, Chiari et al. ICSA-C'22 survey, Lewis et al. on RAG, Pearce et al. S&P'22 on Copilot security, plus GenKubeSec 2024 and Vo et al. COMPSAC'25 — the two closest prior works, both cited in the original Review-1 PDF).

**One field left for manual entry:** `[Designation]` on the title page under the guide's name — the exact academic rank of Dr. S. M. Farooq was not known and was not guessed.

### 7.2 `Agent SecOps - Review 2 Presentation.pptx`

The supplied template edited in place (VIT branding, slide master, layouts, SDG-9 icons all preserved) — 13 slides, all filled, 7 embedded pictures (VIT logo, SDG icons as shipped, plus the architecture diagram and benchmark chart added onto slides 8 and 11).

**One field left for manual entry:** slide 2 ("Approval Mail From Guide") instructs pasting the real approval email screenshot — a genuine message from a real person, not something to fabricate.

### 7.3 The 8 generated figures (`docs/figures/`)

| File | Content | Used in |
|---|---|---|
| `fig1_gantt.png` | 8-phase, 18-week project schedule | Report §2.5 |
| `fig8_benchmark.png` | Detection-per-cloud bars + headline stats | Report §3.2.1, PPT slide 11 |
| `fig2_architecture.png` | Full 4-layer pipeline diagram, BLOCK/PASS split | Report §4.1, PPT slide 8 |
| `fig3_gate_output.png` | **Real terminal capture** of the gate blocking the seeded plan | Report §4.1 |
| `fig4_dfd.png` | Data flow diagram, Level 1, 5 processes/2 data stores | Report §4.2.1 |
| `fig5_usecase.png` | Use case diagram, 4 actors, 7 use cases | Report §4.2.2 |
| `fig6_class.png` | UML class diagram, 3-tier inheritance | Report §4.2.3 |
| `fig7_sequence.png` | Sequence diagram, 6 lifelines, activation bars | Report §4.2.4 |

Regenerate any of these with `python scripts/build_figures.py`, then re-run `build_report.py` / `build_ppt.py` to re-embed.

---

## 8. GitHub Actions pipeline — current status

**As of 2026-10-02: diagnosed, one fix pushed, one fix pending a human action.** Three runs had failed (`#1`–`#3`, commits `8d24232`/`306e01d`/`48610ef`), all for undiagnosed reasons. The 2026-10-02 session fetched the actual job logs for run `#3` via the GitHub API and found **two separate, independent root causes** — not one:

1. **`Terraform validate` failing on the seeded-misconfigurations job.** Root cause: `examples/terraform/noncompliant/main.tf` declared `network_interface_ids = []` on the VM resource, and the AzureRM provider schema requires at least one item — a genuine HCL bug, unrelated to Azure credentials or network state, reproduced locally in seconds once isolated. **Fixed** in commit `6383d04`: added a minimal VNet/Subnet/NIC chain, verified it adds no new rule findings and the gate still blocks with the full set of labelled violations.
2. **`azure/login` (OIDC) failing on the compliant-workload job.** The Azure-side identity was independently re-verified in full — the app registration exists, all three federated credentials have the correct subjects, and Contributor + Storage Data roles are correctly assigned on both resource groups. Since Azure's side is provably correct, the cause is the GitHub repository secrets (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`) — either never saved correctly or stale. **Not yet fixed** — secret values cannot be read back via the API to diagnose further, and three attempts to authenticate `gh` via device code to fix this programmatically all failed for transient reasons (one expired waiting on the human step, one hit a TLS timeout, one hit the 30-minute background ceiling waiting on the human step). The exact values to paste are in §12.

**A separate, real issue found and fixed along the way, unrelated to the pipeline being red:** the live Azure resource had drifted from `infra/demo/main.tf` — the AzureRM provider deprecated the diagnostic setting's `metric` block in favour of `enabled_metric`, and the newer locally-cached provider version wanted to restructure the live resource. Fixed and verified against the real subscription: `terraform plan` now reports zero changes.

**Two workflow characteristics worth remembering:**
1. The workflow plans **two** modules on every push/PR: `infra/demo` (must PASS) and `examples/terraform/noncompliant` (must be BLOCKed — the job is *expected* to report a block verdict, and the workflow's own logic fails the build if it does *not* see a block, which is the gate's self-regression-test).
2. `terraform apply` only runs on `main` after a passing gate, behind the protected `production` environment requiring manual approval.

**To finish this:** reset the three secrets (§12 has the exact current values), then either re-run the failed workflow from the Actions tab or push any commit to trigger a fresh run. Once that's done, run `#4`'s seeded-misconfigurations job (already fixed, re-run not yet observed to completion as of this writing) and the compliant-workload job should both go green, and `apply` becomes reachable behind the `production` environment's manual approval gate.

---

## 9. Documentation index (`docs/`)

| File | Content |
|---|---|
| `PROJECT-CONTEXT.md` | **This file** — the master reference |
| `setup-from-zero.md` | Manual, step-by-step: empty machine -> working pipeline (incl. the dashboard) |
| `dashboard.md` | Dashboard usage, demo script, design rationale |
| `architecture.md` | Full technical design writeup with rationale for every major decision |
| `azure-setup.md` | Azure connection walkthrough, OIDC explanation, troubleshooting table |
| `cost-control.md` | Every cost decision, full cost table, guardrails |
| `team-split.md` | Full presentation scripts per member, anticipated Q&A, demo commands |
| `benchmark-results.md` / `.json` | Detection rate and false-positive numbers, machine-readable + narrative |
| `figures/` | The 8 generated diagrams (see §7.3) plus `_gate_block.txt` (raw captured gate output) |

---

## 10. Quick command reference

```bash
# Run the gate against a fixture (no cloud needed)
python -m agent.cli evaluate --plan examples/plans/azure_noncompliant.plan.json

# Full local demo, no cloud account needed
bash scripts/demo.sh

# Visual dashboard
python -m dashboard.server

# Tests and benchmark
python -m pytest tests/ -q
python scripts/benchmark.py

# Regenerate report / PPT / figures after any change
python scripts/build_figures.py
python scripts/build_report.py
python scripts/build_ppt.py

# The real cycle against live Azure (infra/demo)
cd infra/demo
terraform plan -out tf.plan
terraform show -json tf.plan > plan.json
cd ../..
python -m agent.cli evaluate --plan infra/demo/plan.json   # must be exit 0
cd infra/demo && terraform apply tf.plan

# Session hygiene
bash scripts/azure-cost-check.sh      # before starting
cd infra/demo && terraform destroy    # when done demoing
```

---

## 11. Open items / things not yet done

Tracked here so nothing gets lost between sessions. Items resolved on 2026-10-02 are struck through rather than deleted, so the history of what was ever broken stays visible.

1. ~~GitHub Actions pipeline is red, undiagnosed~~ — **diagnosed in full on 2026-10-02** (§8). Two independent causes found; one fixed and pushed (`6383d04`); the other needs a human to reset 3 GitHub secrets (§12 has the values) because secret values cannot be read back programmatically to verify them, and `gh` device-code auth failed three times for transient reasons rather than succeeding or being refused.
2. ~~Budget alert not set~~ — **fixed on 2026-10-02.** The `az consumption budget create` CLI command is broken on this subscription type; created it instead via a direct `az rest` call to the same underlying API. ₹500/month, alerts at 50/80/100%.
3. **Report title page:** `[Designation]` field still needs the guide's actual academic rank — nobody has supplied it, not something to guess.
4. **PPT slide 2:** still needs the real guide-approval email screenshot pasted in (a genuine record, not something to fabricate). Status as of 2026-10-02: unknown whether this was done for the actual Review-2 presentation — the repo's generated `.pptx` still has the placeholder text, but that may not be the file that was actually presented from.
5. **Report Table of Contents page numbers** are still estimates from before the 8 figures were embedded. Likely moot now — Review 2 has already happened (`git log` shows a `final commit after review2`) — but worth a final check before any formal submission that still uses this exact file.
6. ~~Generated docs/figures/scripts untracked~~ — **resolved.** All of it (templates, generated `.docx`/`.pptx`, `docs/figures/`, the three `scripts/build_*.py` generators) is now committed (see the `48610ef`/`d528e36` history in §13) — the project maintainer's call was to keep them in version control despite being large binaries.
7. ~~Office lock files not gitignored~~ — **fixed on 2026-10-02** (`6383d04`).
8. **`terraform destroy` not yet run** — the live Azure resources in §6.2 are still deployed, now with zero config drift and a budget alert as a safety net. Tear down before a long gap between sessions, or once no further live-Azure demonstration is needed.

---

## 12. Key facts to never re-derive

- Repo: `github.com/GAURISHTODI/Agent-SecOps`, remote already configured, pushes work via existing credential manager (not `gh` CLI auth, which has now failed to complete across two separate sessions — stop retrying it as a way to *read* repo state or secrets; it remains worth one or two attempts per session if the goal is to *write* something, like resetting secrets, since it occasionally does complete).
- Azure login for this project's deployment: `gaurishtodi@gmail.com`, NOT the VIT student account.
- Storage account names are globally unique and were randomly suffixed at creation time (`secopstfstate4853`, `secopsdevcindata`) — do not assume these names are reproducible if resources are recreated.
- The offline reasoner is the CI default (`SECOPS_REASONER=offline` pinned in the workflow) — no PR can accidentally spend money via the LLM path.
- 42 is the seeded-violation ground truth count; do not recompute or vary this without updating `scripts/benchmark.py`'s `GROUND_TRUTH` dict and every document that cites it.
- **Current correct values for the three GitHub Actions secrets** (re-verified live against Azure on 2026-10-02 — if the pipeline is still failing the `azure/login` step and these were already set, the secrets are the thing to re-check first):
  ```
  AZURE_CLIENT_ID       = 01548123-a938-4fd1-89b3-979a8bb6cab3
  AZURE_TENANT_ID       = da8d0e2e-bbb4-416a-a0c4-aef68e06c869
  AZURE_SUBSCRIPTION_ID = f2c8dcf2-da4a-43ae-9b8d-51ada86f4c15
  ```
  Repository variables `TFSTATE_RG=secops-tfstate-rg` and `TFSTATE_SA=secopstfstate4853` should also exist. Set at [github.com/GAURISHTODI/Agent-SecOps/settings/secrets/actions](https://github.com/GAURISHTODI/Agent-SecOps/settings/secrets/actions).
- The app registration `secops-github-oidc` (appId `01548123-a938-4fd1-89b3-979a8bb6cab3`) and its 3 federated credentials (`gh-main`, `gh-pr`, `gh-env-production`) and role assignments were fully re-verified correct on 2026-10-02 — if the pipeline is broken again later, don't re-audit the Azure side from scratch; check the GitHub secrets first, since that's the side that can't be read back to confirm.

---

## 13. Session log — 2026-10-02 (second working session)

A second session, three weeks after the first, picked this project back up with the instruction to "finish it fully." What actually happened, in order:

1. **Environment was broken on this machine.** `pip install -r requirements.txt` had never been run; `pytest` failed on `ModuleNotFoundError: No module named 'yaml'`. Fixed by installing requirements; 63/63 tests passed afterward.
2. **Checked git/CI state first, before touching anything.** Found a `d528e36` "baseline checkpoint" commit (an artifact of the harness's own auto-commit mechanism from earlier in this same session, before this account was in control of it) had already been amended into `48610ef` and pushed — pre-existing state, not something this session caused or needed to fix.
3. **Pulled real CI failure logs via the GitHub REST API** (`gh` wasn't authenticated, so used unauthenticated API access where public repos allow it) rather than guessing at causes. Found the three historical runs (`#1`–`#3`) all failed, and got job-level and step-level detail on run `#3`.
4. **Reproduced the `terraform validate` failure locally** in `examples/terraform/noncompliant` and found the real cause in under a minute: `network_interface_ids = []` violates the AzureRM provider's `MinItems: 1` schema constraint. Fixed by adding a minimal VNet/Subnet/NIC chain; checked first that no rule targets those resource kinds, so the benchmark's 42-violation ground truth stays exact.
5. **Independently re-audited the entire Azure-side OIDC identity** (app registration, federated credential subjects, role assignments) via `az` rather than assuming it had broken. Found it fully correct, which isolated the `azure/login` failure to the GitHub secrets — the one place state can't be read back to confirm.
6. **Found and fixed a real drift bug that wasn't on anyone's radar:** running a fresh `terraform plan` against the live Azure deployment (not a fixture) showed the real resource had drifted — the AzureRM provider deprecated the diagnostic setting's `metric` block. Fixed in `infra/demo/main.tf`; replan showed zero changes.
7. **Created the budget alert that had been blocked since the first session** by going around the broken `az consumption budget create` CLI command and calling the same underlying REST API directly.
8. **Attempted `gh auth login` via device code three times** to fix the GitHub secrets programmatically rather than asking for manual entry. All three failed for different transient reasons (user hadn't completed it yet / TLS timeout / 30-minute background ceiling) rather than being refused or erroring on the GitHub side — concluded this path is unreliable in this environment and switched to asking for either manual secret entry or a personal access token.
9. **Committed and pushed everything that didn't depend on the blocked secrets** (`6383d04`) rather than waiting idle, since fixing CI for the seeded-misconfigurations job didn't require the Azure secrets at all.
10. Triggered run `#4` by the push in step 9 and watched it live via the API. *(If you're reading this and run #4's outcome isn't mentioned further down in this document, the session ended before it was recorded here — check the Actions tab directly.)*

**Net result:** one of the two CI failure causes fixed and verified; the other fully diagnosed and isolated to a single, specific manual action, with the exact values needed already in §12 rather than requiring re-diagnosis.
