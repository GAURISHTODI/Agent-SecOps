# Team Split — Three-Way Ownership

Project ID 19727UG01 · Agent SecOps · Guide: Dr. SM Farooq

The work divides into three modules with clean seams. Two are **self-contained and precisely explainable** — you can present them completely without needing to reason about the rest of the system. The third carries the **architectural and research narrative** and needs the full context, because it is the part that answers "why is this a project and not a script?"

| | Owner | Module | Nature |
|---|---|---|---|
| **A** | **Akshat Gupta** | Plan ingestion + deterministic CAF/WAF rule engine | Self-contained, precise |
| **B** | **Bhumika Singh** | CI/CD pipeline, Terraform, Azure integration, reporting | Self-contained, precise |
| **C** | **Gaurish Todi** | Reasoning layer, policy/verdict engine, evaluation, architecture | Full context, integrative |

---

# Module A — Akshat Gupta
## Plan Ingestion and the Deterministic Rule Engine

### What you own

| File | What it does |
|---|---|
| `agent/models.py` | The data model: `Resource`, `Finding`, `Pillar`, `Severity`, `Verdict` |
| `agent/plan_parser.py` | Terraform plan JSON → normalized, cloud-agnostic resources |
| `agent/rules/base.py` | Rule base class and registry |
| `agent/rules/caf.py` | 7 CAF rules — governance, landing zone, cost, identity |
| `agent/rules/waf.py` | 15 WAF rules — all six pillars |
| `tests/test_plan_parser.py`, `tests/test_rules.py` | 45 of the 63 tests |

### Your two-minute explanation

> "My module turns a Terraform plan into a compliance verdict input.
>
> Terraform emits `resource_changes[]` — for each resource, its type, what action is planned, and the full `after` state. I parse that into `Resource` objects, and the key step is that I assign each one a **canonical `Kind`**. `azurerm_storage_account`, `aws_s3_bucket` and `google_storage_bucket` all become `Kind.OBJECT_STORAGE`. That single mapping table is why the gate is cloud-agnostic: I write a rule once against `OBJECT_STORAGE` and it works on all three clouds. There's a test that asserts exactly this.
>
> Then 22 rules run over those resources. Each rule is a class with an id, a **pillar**, a severity, the kinds it applies to, and a `check()` method that returns an explanation or nothing. The pillar is mandatory — it's an enum, so a finding literally cannot exist without naming the CAF or WAF pillar it violates. That's what lets the report say *which* pillar was broken instead of just failing.
>
> Rules are parameterised, not hardcoded. The approved region list, the mandatory tags, the sensitive port list — all overridable from `policies/policy.yaml`, so an organisation adapts the gate without touching Python."

### The three details that show depth

**1. `["delete", "create"]` is a replacement, not a delete.**
> "Terraform encodes a forced replacement as both actions in one list. If I'd treated that as a delete, every create-time rule would skip it — and someone could bypass the entire gate by forcing a replacement. So I collapse it to `Action.REPLACE` and treat it as mutating. It's a test case."

**2. The firewall/database misclassification.**
> "`azurerm_mssql_firewall_rule` contains the substring `sql`, so my heuristic fallback classified it as a database. That produced three false positives on one object — missing tags, missing cost centre, missing diagnostics — on a firewall rule that has no tags, no SKU and no logs. I fixed it by matching firewall patterns *before* database patterns, and it's a regression test now. It's a good example of why the false-positive tests matter as much as the detection tests."

**3. Unknown types fall through to heuristics, not to silence.**
> "If a provider ships a resource type I've never seen, I don't ignore it — I match on substrings and put it in the closest bucket so it still gets checked. Silently skipping unknown resources is how a gate develops blind spots."

### Likely questions

**"How is this different from Checkov?"**
> "At my layer alone, it isn't very different — that's the honest answer. My layer is deterministic rules, roughly what a static scanner gives you. The difference is two things: I run on the *plan* rather than the HCL source, so I see fully resolved values after variables and modules are evaluated; and my findings feed a reasoning layer on top, which is Gaurish's module and where the actual novelty is."

**"Why 22 rules? Why not 200?"**
> "22 is enough to cover every CAF governance area and all six WAF pillars, which is what validates the architecture. Scaling to 200 is adding entries to a registry — it's volume, not new engineering. We chose to demonstrate breadth across pillars rather than depth in one."

**"How do you avoid false positives?"**
> "Two ways. Every rule is tested in both directions — it must fire on the violation and stay silent on the compliant equivalent. And unknown values are never violations: when Terraform computes an attribute at apply time it shows up as `null`, and I treat that as 'not a violation' rather than guessing. The benchmark reports zero false positives on the compliant module."

### Demo you run

```bash
python -m agent.cli rules                     # the catalogue
python -m agent.cli explain WAF-SEC-004       # framework traceability
python -m pytest tests/test_rules.py -v       # both-directions testing
```

---

# Module B — Bhumika Singh
## CI/CD Pipeline, Terraform, Azure Integration and Reporting

### What you own

| File | What it does |
|---|---|
| `.github/workflows/secops-gate.yml` | The pipeline the gate lives inside |
| `infra/demo/` | Minimal compliant Azure module (`main.tf`, `variables.tf`, `outputs.tf`) |
| `examples/terraform/noncompliant/` | The seeded misconfiguration module |
| `scripts/azure-bootstrap.sh` | Azure setup: OIDC, state backend, budget |
| `scripts/azure-cost-check.sh`, `azure-destroy.sh` | Credit guardrails |
| `agent/report.py` | Markdown / JSON / SARIF renderers |
| `agent/cli.py` | The command the pipeline runs |
| `dashboard/` | The demo web UI (React frontend + Python backend) |
| `docs/azure-setup.md`, `docs/cost-control.md` | Setup and cost documentation |

### Your two-minute explanation

> "My module is everything that makes the agent an actual pipeline gate rather than a script someone runs by hand.
>
> The workflow has three jobs. First the agent's **own unit tests** run — if the gate's tests fail, its verdicts are meaningless, so nothing downstream is allowed to proceed. Then the plan-and-gate job runs `terraform plan`, converts it to JSON with `terraform show -json`, and hands it to the agent. The agent's **exit code is the pipeline decision**: 0 passes, 2 blocks. Apply only runs on main, only after a passing gate, and only behind a protected environment that requires a human approval — so there's a second control on top of the automated one.
>
> The clever part is that the matrix plans **two** modules on every PR. The compliant one must pass, and the seeded misconfiguration module must be **blocked**. If the seeded module ever stops being blocked, the build fails — that's the regression test for the gate itself, running in CI on every change.
>
> On output, the agent produces three formats: Markdown that gets posted as a PR comment, JSON for machines, and SARIF that lands in GitHub's Security tab as tracked alerts. The PR comment updates in place rather than adding a new comment on every push."

### The three details that show depth

**1. OIDC federation — no stored secret.**
> "The normal approach is to create a service principal secret and paste it into GitHub Secrets. That's a long-lived, copyable credential — exactly what our own `WAF-SEC-006` and `CAF-IAM-001` rules exist to catch. Instead we use OIDC federation: GitHub presents a signed token describing the repo and branch, Azure trusts that issuer for specific registered subjects and exchanges it for a token valid for minutes. Nothing long-lived is stored anywhere. The project holds itself to the standard it enforces."

**2. Least privilege on our own service principal.**
> "The bootstrap grants Contributor scoped to the *resource groups*, not the subscription. If we'd granted it at subscription scope, our own `CAF-IAM-001` rule would flag it as critical. We ran the gate against our own infrastructure design."

**3. The cost architecture.**
> "The demo module deliberately has no VM, no AKS, no SQL Server, no App Service plan and no private endpoint — those are the five things that actually drain credits. It's a resource group, a storage account, and a Log Analytics workspace with a 0.1 GB/day hard cap so ingestion *stops* rather than bills. Under ₹50 a month, usually under ₹10.
>
> And here's the key insight: the expensive misconfigurations — a ₹25,000/month D8s VM, an AKS cluster — are demonstrated through **plan-only fixtures**. The gate reads a plan, not a deployment, so we can test the most expensive violations at exactly zero cost. That isn't a workaround; it's the reason gating at plan time is the right architecture."

### Likely questions

**"Why gate at plan time instead of using Azure Policy?"**
> "Azure Policy evaluates resources that already exist, or blocks at the ARM layer after the pipeline has already committed to deploying. By then you've spent money, and for something like a public storage container the data may already be exposed — industry benchmarks put average misconfiguration dwell time at 180+ days. The plan JSON is the earliest point where you know the fully resolved set of changes and the last point before anything is created. They're complementary, but plan-time is cheaper and earlier."

**"What if the agent crashes? Does the pipeline hang?"**
> "No. Exit code 3 is a usage or parse error, and the workflow treats a non-zero gate exit as a failure — it fails closed for real errors. But the agent is written so a malformed plan attribute produces a verdict rather than a traceback; there's a test that feeds it deliberately corrupt attribute types. And if the optional LLM endpoint is unreachable, it degrades to the offline reasoner and says so in the report rather than breaking the build."

**"How would a team adopt this on an existing repo with 100 violations?"**
> "`--soft-fail`. It always exits 0, so you get the full report without blocking anyone. Fix the backlog, then turn enforcement on. A gate that can't be adopted incrementally doesn't get adopted."

### Demo you run

```bash
python -m dashboard.server                # the visual demo -- lead with this
```
Show the compliant plan passing, then the seeded plan blocking, then toggle the
reasoning layer off and back on. Then the command-line reality behind it:

```bash
bash scripts/azure-cost-check.sh          # what exists and what it costs
cd infra/demo && terraform plan -out=tf.plan
terraform show -json tf.plan > plan.json
cd ../.. && python -m agent.cli evaluate --plan infra/demo/plan.json
# only then: terraform apply
```
Then show a live PR with the gate comment and the Security tab.

---

# Module C — Gaurish Todi
## Reasoning Layer, Policy Engine, Evaluation and Architecture

> **This is the integrative module.** Akshat can present the rule engine without knowing how the pipeline works, and Bhumika can present the pipeline without knowing how a rule is written. You cannot present this module without understanding both — because your job is to explain why the two of them together constitute a *research contribution* rather than a well-built script.

### What you own

| File | What it does |
|---|---|
| `agent/knowledge/caf_waf_kb.yaml` | The CAF/WAF knowledge base the reasoner reads |
| `agent/reasoner/base.py` | Retrieval, redaction, prompt construction |
| `agent/reasoner/offline.py` | Free deterministic reasoner (CI default + control arm) |
| `agent/reasoner/llm.py` | Azure OpenAI / Anthropic with structural cost controls |
| `agent/reasoner/__init__.py` | Reasoner factory with graceful fallback |
| `agent/engine.py` | Three-layer orchestration and verdict production |
| `agent/config.py` | Thresholds, rule overrides, time-boxed waivers |
| `scripts/benchmark.py` | The evaluation harness and ground truth |
| `docs/architecture.md`, `docs/benchmark-results.md` | The technical narrative |
| `tests/test_engine.py` | 18 end-to-end tests |

---

## C.1 — The research gap, stated precisely

This is your opening, and it must be sharp.

> "Existing policy-as-code tools — Checkov, tfsec, OPA, Sentinel — enforce rules that someone has already written down. That's necessary but bounded: they can only catch what a human anticipated and encoded.
>
> CAF and WAF aren't rule sets. They're thousands of words of narrative architectural guidance — 'prefer identity-based authentication over shared keys', 'production data should survive the loss of a datacentre', 'grants should be scoped to the narrowest resource that satisfies the requirement'. Most of that has never been turned into an executable rule, and much of it is contextual in a way a static rule can't express.
>
> The literature confirms LLMs can outperform rule-based scanners at misconfiguration detection — GenKubeSec for Kubernetes, Vo et al. 2025 for Terraform code smells. But no existing work embeds an LLM reasoning agent as a **CI/CD pipeline gate** that checks Terraform **plans** against CAF/WAF governance **before deployment**, across multiple clouds. That specific combination is our gap."

Then land the number:

> "We measured it. 42 seeded violations across Azure, AWS and GCP. Deterministic rules alone — which is roughly what a static scanner gives you — catch 37, 88.1%. Adding the reasoning layer catches all 42. **Five violations are recoverable only by reasoning over framework guidance**, with zero false positives on the compliant module. That five is the contribution, quantified."

---

## C.2 — The three-layer architecture, and why it is three

> "The gate is three layers, and the separation is the design.
>
> **Layer 1, deterministic rules.** Fast, free, explainable, confidence 1.0. This handles everything expressible as an if-statement.
>
> **Layer 2, reasoning.** This handles what the frameworks *imply* but no rule encodes. It receives the resource plus retrieved framework guidance plus the list of what Layer 1 already found, and is explicitly instructed not to repeat it — so it only ever adds.
>
> **Layer 3, policy.** Thresholds and waivers. The gate is a control, and controls need an escape hatch that doesn't become a hole.
>
> Why not just one LLM call over the whole plan? Three reasons. Cost — Layer 1 is free and catches 88%, so paying a model to re-derive it is waste. Determinism — a build gate that gives different answers on identical input is unusable, so the blocking decisions must come from deterministic rules. And explainability — when the gate blocks a deploy, the developer deserves 'you violated WAF-SEC-004, here is the pillar, here is the HCL fix', not a paragraph of model prose."

---

## C.3 — How the reasoning layer actually works

This is your technical core. Be specific.

**Retrieval.**
> "The knowledge base has two parts: the pillars with their principles in prose, and a `kind_focus` index mapping each canonical resource kind to the pillars worth considering plus specific watch-points. When a managed database arrives, I retrieve only the three pillars indexed for databases and their watch-points — not the entire CAF/WAF corpus.
>
> It's retrieval-augmented generation, but the retrieval is keyed on a **type system** rather than embeddings. That's cheaper, and it's fully deterministic in what it selects — I can tell you exactly what guidance any given resource will be judged against, which you can't do with a vector search."

**Two implementations, one interface.**
> "`OfflineReasoner` is 12 hand-written probes, each corresponding to a watch-point. Free, milliseconds, deterministic — the CI default. `LLMReasoner` talks to Azure OpenAI or Anthropic over plain urllib, no vendor SDK.
>
> The offline reasoner isn't just a cheap fallback — it's the **control arm** of the experiment. The claim is that LLM reasoning finds things neither the rules nor good heuristics catch. You cannot measure that without a deterministic baseline to measure against."

**Four guardrails on the model.**
> "An LLM in a build gate is a non-deterministic, untrusted component on a control path. So:
>
> 1. **It can't invent resources.** Findings whose address isn't in the submitted set are dropped.
> 2. **It can't duplicate Layer 1.** Rule findings are passed in as `already_reported` and the prompt forbids repeating them. There's a test that asserts zero title overlap per resource between the layers.
> 3. **It can't fail a build by default.** `fail_on_reasoner_findings: false`. Reasoning findings appear in full and can escalate to 'remediate', but only deterministic rules can block — until an organisation has measured the reasoner's precision and explicitly opts in.
> 4. **It can't break the pipeline.** Endpoint down, malformed JSON, timeout — all degrade to an informational finding saying the verdict rests on rules alone. A gate that fails closed on a model outage is worse than no gate."

**Cost controls, structural not advisory.**
> "Triage — only resources whose kind is in the knowledge base are candidates. A hard cap of 12 resources per run, so a 200-resource plan still sends 12. Redaction — secrets stripped, strings truncated at 160 characters, lists capped at 5 elements, because prompt size *is* the bill. And a disk cache keyed on model plus prompt hash, so re-running an unchanged plan costs nothing.
>
> Net effect: under ₹0.10 per gated run on `gpt-4o-mini`. And CI pins `SECOPS_REASONER: offline`, so no pull request can spend money by accident."

---

## C.4 — Policy: waivers that expire

> "Every real compliance system dies the same way: someone adds an exception 'temporarily', and five years later nobody remembers why it's there.
>
> So a waiver here requires a reason, matches by glob so it can't be over-broad by accident, and **expires**. When it expires it stops suppressing its finding *and* the report explicitly calls out that it lapsed. There are two tests — one that a valid waiver suppresses and records its reason, one that an expired waiver stops suppressing and gets reported. Accepted risk can't quietly become permanent."

---

## C.5 — The evaluation, and why it has three numbers

> "The success metric in our proposal was 'catching a broader class of CAF/WAF violations than existing static scanners, measured against a seeded test set'. To test that honestly you need three numbers, not one.
>
> **Recall** — 42 seeded violations, all detected. But recall alone is gameable: a gate that flags everything has perfect recall and is useless.
>
> **False positives** — zero on the compliant module. This is what decides whether anyone leaves the gate switched on. A gate that fails clean code gets disabled by the team that owns it, so we treat this as equally important.
>
> **Marginal contribution of reasoning** — 5 violations. This is the actual research claim, because the rules layer approximates what a static scanner already does. Running the same fixtures with the reasoner disabled and comparing is the experiment."

**Be ready to state the limitations before you're asked.** It's the strongest move available to you:

> "Three honest caveats. The ground truth is self-authored — 42 violations we seeded and labelled ourselves; a stronger evaluation would use an independent corpus of public modules with known CVEs. The benchmark matches on (resource, pillar) rather than exact rule id, which is the fair test — was the violation surfaced to the developer? — but it's more lenient than exact matching, and we say so in the code. And the offline reasoner is heuristics, not reasoning; it's a faithful control arm and a free default, but the genuine framework-intent reasoning is the LLM path."

---

## C.6 — Questions aimed at you specifically

**"Why should I trust an LLM to gate my production deployments?"**
> "You shouldn't, and by default the system doesn't let you. `fail_on_reasoner_findings` is false — the LLM can't block a build. It surfaces concerns in the report and can escalate to 'remediate', but blocking is reserved for deterministic rules with confidence 1.0. Organisations opt into LLM-blocking only after measuring its precision on their own workloads. That's a deliberate architectural stance: the reasoning layer widens *coverage*, the rules layer holds *authority*."

**"What happens when the model hallucinates a violation?"**
> "Three filters. Structurally, findings referencing a resource that isn't in the submitted set are dropped — it can't invent infrastructure. Statistically, findings below 0.6 confidence are dropped as noise. And architecturally, even a surviving hallucination is advisory and can't block. The worst case is a developer reading one wrong sentence in a report, not a broken deployment."

**"Isn't this just RAG with extra steps?"**
> "It's RAG, but the interesting part is what it retrieves *over*. Normal RAG retrieves documents by embedding similarity. Here retrieval is keyed on a type system — a canonical resource kind derived from the plan — so I know deterministically which guidance any resource will be judged against. And the retrieval index is authored alongside the rule engine, which is what lets Layer 2 know precisely what Layer 1 already covered. That coupling is what makes the two layers additive instead of redundant."

**"How does this scale to a real organisation?"**
> "The rule engine is a registry — adding rules is entries, not engineering. The knowledge base is YAML, so a platform team extends framework coverage without writing Python. `policies/policy.yaml` handles per-org tuning: thresholds, region lists, mandatory tags, waivers. The realistic scaling limit isn't rules, it's the LLM cost on very large plans, which is why the 12-resource cap and the cache exist. Beyond that you'd triage by blast radius — reason about resources that are new or network-facing, not every unchanged item."

**"What's the next step — TRL 5?"**
> "Three things. Replace the self-authored ground truth with an independent corpus. Run the LLM reasoner at volume to get real precision numbers, which is what would justify enabling `fail_on_reasoner_findings`. And deepen the AWS and GCP rule content — the architecture is proven cloud-agnostic by tests, but the rule *content* is Azure-weighted, matching our CAF/WAF framing."

---

## C.7 — Your demo

```bash
# 1. The layered verdict, both layers visible in the report
python -m agent.cli evaluate --plan examples/plans/azure_noncompliant.plan.json \
  --markdown out/report.md --format markdown

# 2. The experiment: same plan, reasoning disabled
python -m agent.cli evaluate --plan examples/plans/azure_noncompliant.plan.json \
  --no-reasoner

# 3. The measurement
python scripts/benchmark.py

# 4. Waiver expiry
python -m pytest tests/test_engine.py -k waiver -v
```

Step 2 into step 3 is the money shot: show the same plan losing findings when reasoning is switched off, then show the benchmark quantifying it.

---

# Presentation running order

| Slot | Who | Content | Time |
|---|---|---|---|
| 1 | **Gaurish** | Problem, research gap, three-layer architecture, where the agent sits | 3 min |
| 2 | **Akshat** | Plan parsing, canonical kinds, the rule engine, live `rules` + `explain` | 4 min |
| 3 | **Bhumika** | Dashboard demo, pipeline, OIDC, Terraform modules, live PR with gate comment, cost design | 4 min |
| 4 | **Gaurish** | Reasoning layer, guardrails, waiver expiry, benchmark, limitations, next steps | 4 min |
| 5 | All | Questions | — |

Gaurish opens and closes because the framing and the evidence are both his; the middle two sections are the concrete build. Each of Akshat's and Bhumika's sections stands alone — neither needs the other's material to make sense, which is what makes them safe to present independently under time pressure.

---

# Integration checklist

Before each review, run and confirm all five are green:

```bash
python -m pytest tests/ -q                      # 63 passed
python scripts/benchmark.py                     # 100% detection, 0 FP
python -m dashboard.server                      # dashboard loads, all 3 tabs
bash scripts/demo.sh                            # full walkthrough
bash scripts/azure-cost-check.sh                # nothing unexpected running
# and: open a PR, confirm the gate comment appears
```
