# Architecture

How Agent SecOps works, layer by layer, and why each layer is built the way it is.

---

## 1. Where the agent sits, and why exactly there

```
Developer commits .tf
        │
        ▼
GitHub Actions triggered
        │
        ▼
terraform plan -out=tf.plan
terraform show -json tf.plan  ──►  plan.json
        │
        ▼
┌───────────────────────────────────────────────┐
│              AGENT SECOPS GATE                │
│                                               │
│  plan_parser  →  normalized Resource objects  │
│       │                                       │
│       ├─► Layer 1: deterministic CAF/WAF rules│
│       │            (22 rules, confidence 1.0) │
│       │                                       │
│       ├─► Layer 2: framework reasoning        │
│       │            (what no rule encodes)     │
│       │                                       │
│       └─► Layer 3: org policy                 │
│                    thresholds + waivers       │
│                          │                    │
│                     verdict + report          │
└──────────────────────────┬────────────────────┘
                           │
         BLOCK ◄───────────┴───────────► PASS
           │                              │
   report on the PR              terraform apply
   exit 2, nothing deployed      → Azure / AWS / GCP
```

The position is the design. Three alternatives were considered and rejected:

| Where you could gate | Why not |
|---|---|
| On the `.tf` source (like Checkov) | HCL is not the truth. Variables, modules, `count`, `for_each` and data sources mean the source does not tell you what will actually be created. |
| After `apply`, via Azure Policy or Defender | The resource already exists. Money has been spent and, for a public storage account, data may already be exposed. Industry benchmarks put the average misconfiguration dwell time at 180+ days. |
| In code review, by a human | Does not scale to dozens of PRs a day across three clouds, and reviewers miss exactly the subtle combinations that matter. |

The plan JSON is the earliest point at which the *fully resolved* set of changes is known and the *last* point before anything is created. That is a single moment in the lifecycle, and it is where the agent lives.

---

## 2. Layer 0 — Normalization (`plan_parser.py`)

Terraform emits `resource_changes[]`, each with a type, an action list, and a `before`/`after` state. The parser turns that into `Resource` objects carrying a **canonical `Kind`**.

```python
azurerm_storage_account  ┐
aws_s3_bucket            ├──► Kind.OBJECT_STORAGE
google_storage_bucket    ┘
```

This one mapping table is the entire multi-cloud story. A rule is written once against `Kind.OBJECT_STORAGE` and works on all three clouds. `tests/test_plan_parser.py::test_same_kind_across_three_clouds` asserts exactly this.

Three details worth defending in a viva:

- **`["delete", "create"]` is a replacement, not a delete.** Terraform encodes replacement as both actions. A replace re-creates the resource, so every create-time rule must run against it. Missing this would let anyone bypass the gate by forcing a replacement.
- **Unknown types fall through to substring heuristics**, not to silence. A brand-new provider resource lands in a plausible bucket and still gets checked. Silently ignoring unknown resources is how gates develop blind spots.
- **Firewall rules are matched before databases.** `azurerm_mssql_firewall_rule` contains the substring `sql`. Classifying it as a database produced three false positives (missing tags, missing cost centre, missing diagnostics) on an object that has no tags, no SKU and no logs. This is a regression test now.

Nested blocks are the other sharp edge: Terraform renders a single nested block as a one-element list, so `Resource.get("network_rules.default_action")` transparently steps through `after["network_rules"][0]["default_action"]`.

---

## 3. Layer 1 — Deterministic rules (`rules/`)

22 rules, each a small class with metadata and a `check()` method returning an explanation string or `None`.

```python
@register
class OpenIngress(Rule):
    id = "WAF-SEC-004"
    pillar = Pillar.WAF_SECURITY
    severity = Severity.CRITICAL
    kinds = (Kind.NETWORK_FIREWALL,)
    rationale = "WAF Security requires minimal network exposure..."
    params = {"sensitive_ports": [22, 3389, 3306, 5432, 1433, 27017, 6379]}
```

Properties that matter:

- **Every rule names a pillar.** `Pillar` is an enum covering CAF's four governance areas and WAF's six pillars. The project brief requires reports that say *which pillar* was violated, so the type system enforces it — a finding cannot exist without one.
- **Every rule carries a `rationale`.** This is the framework guidance in prose. It feeds `agent.cli explain`, and a test asserts no rule ships without one. Documentation is part of the deliverable, so it is tested.
- **Rules are parameterised, not hardcoded.** `params` are overridable from `policies/policy.yaml`, so an organisation changes its approved regions or mandatory tags without touching Python.
- **Confidence is always 1.0.** A deterministic rule either matched or it did not. This is what distinguishes Layer 1 findings from Layer 2 findings in the report and in the verdict logic.

### Coverage

| Framework | Area | Rules |
|---|---|---|
| CAF | Governance (tags, naming) | 2 |
| CAF | Landing Zone (region, network boundary, public IP) | 3 |
| CAF | Cost Management | 1 |
| CAF | Identity | 1 |
| WAF | Security | 6 |
| WAF | Reliability | 3 |
| WAF | Cost Optimization | 2 |
| WAF | Operational Excellence | 2 |
| WAF | Performance Efficiency | 1 |
| WAF | Sustainability | 1 |

### Cross-resource checks

Some questions cannot be answered by looking at one resource. "Does this storage account have diagnostics?" depends on a *separate* `azurerm_monitor_diagnostic_setting` elsewhere in the plan pointing back at it. The engine resolves these links in `_link_diagnostics()` before rules run, annotating the target resource. A rule examining resources in isolation could never see it.

---

## 4. Layer 2 — Reasoning (`reasoner/`)

**This is the layer the project exists for.**

Layer 1 is, roughly, what Checkov already gives you: violations of rules someone wrote. Layer 2 answers the harder question — *does this break CAF/WAF intent that nobody ever turned into a rule?*

### The knowledge base

`agent/knowledge/caf_waf_kb.yaml` holds the framework guidance in two parts:

- **`pillars`** — each pillar's guiding question and its principles in prose.
- **`kind_focus`** — a retrieval index mapping each canonical kind to the pillars worth considering and specific things to watch for.

```yaml
kind_focus:
  managed_database:
    pillars: [WAF:Security, WAF:Reliability, CAF:LandingZone]
    watch_for:
      - "Public endpoint plus a permissive firewall rule (0.0.0.0 start address)."
      - "Administrator credentials supplied inline rather than from a secret store."
```

This index is what makes the layer affordable. Instead of pasting the entire CAF/WAF corpus into every prompt, the reasoner retrieves the handful of principles indexed against the resource in front of it. It is retrieval-augmented generation, with the retrieval keyed on a type system rather than on embeddings — which is both cheaper and fully deterministic in what it selects.

### Two interchangeable implementations

Both implement the same interface and receive the same retrieved context:

**`OfflineReasoner`** — 12 hand-written probes, each corresponding to a `watch_for` line. Free, runs in milliseconds, deterministic. It is the CI default, and it is also the **control arm**: the research claim is that LLM reasoning finds violations that neither the rules nor these heuristics catch, and you cannot measure that without a deterministic baseline.

**`LLMReasoner`** — Azure OpenAI or Anthropic over plain `urllib` (no vendor SDK, so the runner installs two packages total). Cost controls are structural, not advisory: triage, a 12-resource cap, redaction and truncation, and a disk cache keyed on model + prompt hash.

### Guardrails on model output

An LLM in a build gate is an untrusted, non-deterministic component sitting on a control path. Four constraints follow:

1. **It cannot invent resources.** Findings whose address is not in the submitted set are dropped.
2. **It cannot duplicate Layer 1.** Rule findings for each resource are passed in as `already_reported`, and the prompt forbids repeating them. `test_reasoner_never_duplicates_a_rule_finding` enforces this.
3. **It cannot fail a build by default.** `fail_on_reasoner_findings: false` means reasoning findings are advisory. They appear in full in the report and can escalate a verdict to `remediate`, but only deterministic rules can `block` — until an organisation has measured the reasoner's precision and opts in.
4. **It cannot break the pipeline.** Endpoint down, malformed JSON, timeout — all degrade to an informational finding saying the verdict rests on rules alone. A gate that fails closed on a model outage would be worse than no gate.

Low-confidence output (below `min_confidence: 0.6`) is dropped as noise.

---

## 5. Layer 3 — Policy (`config.py`)

The gate is a control, and controls need an escape hatch that does not become a hole.

**Thresholds.** `block_at: high`, `remediate_at: medium`. Verdict aggregation is a fold over findings.

**Rule overrides.** Enable/disable, change severity, or override parameters, all from YAML.

**Waivers — time-boxed by construction.**

```yaml
waivers:
  - rule_id: CAF-GOV-002
    resource: "azurerm_storage_account.tfstate"
    reason: "Backend storage predates the naming standard; tracked in PROJ-114."
    expires: "2026-12-31"
```

Three properties: a waiver requires a reason; it matches by glob so it cannot be over-broad by accident; and it **expires**. An expired waiver stops suppressing its finding *and* is called out in the report. "Accepted risk" cannot quietly become permanent — which is the failure mode of every exception process ever built.

---

## 6. Output (`report.py`)

Three audiences, three renderers:

| Format | Audience | Where it lands |
|---|---|---|
| Markdown | The developer | PR comment (updated in place) + job summary |
| JSON | Machines | Artifact; the benchmark harness consumes it |
| SARIF 2.1.0 | Security tooling | GitHub Security tab, as tracked alerts |

The Markdown report gives a verdict banner, a per-pillar violation table, findings grouped by resource with severity, rule id, pillar, explanation, **a copy-pasteable HCL fix**, and provenance (deterministic rule vs reasoning layer with a confidence percentage). Waived findings are in a collapsed section — visible, not hidden.

The brief asks for "which rule/pillar was violated and a suggested fix, not just a fail flag". `test_markdown_report_names_pillar_and_fix` asserts the pillar name and an ````hcl` block are both present.

---

## 7. The pipeline contract

Exit codes are the entire integration surface:

| Code | Verdict | Effect |
|---|---|---|
| 0 | `pass` | `apply` proceeds |
| 1 | `remediate` | Warn; proceeds with `--soft-fail` |
| 2 | `block` | Pipeline stops |
| 3 | error | Bad plan or usage |

`--soft-fail` exists for adoption: onboarding an existing repository with a hundred pre-existing violations, you run report-only first, fix the backlog, then turn enforcement on. A gate that cannot be adopted incrementally does not get adopted.

The workflow plans **both** modules on every PR: the compliant one must pass, and the seeded one must be blocked. **The seeded module failing to be blocked fails the build** — that is the regression test for the gate itself, running in CI on every change.

---

## 8. Testing strategy

63 tests, three levels:

- **Parser** — provider detection, kind mapping across three clouds, replace-as-create, the firewall/database regression, AWS tag-list and GCP label normalization.
- **Rules** — every rule tested in **both** directions: it must fire on the violation and stay silent on the compliant equivalent. False-positive tests are as numerous as detection tests, because a gate that cries wolf gets switched off.
- **Engine** — verdicts, waiver expiry, threshold changes, both layers contributing, no duplication between layers, all three report formats, CLI exit codes, and a deliberately malformed plan that must produce a verdict rather than a traceback.

Plus `scripts/benchmark.py`, which measures recall against 42 labelled violations and false positives against the clean module, and reports the reasoning layer's marginal contribution. Current: **100% detection, 0 false positives, 5 violations recovered by reasoning alone.**

---

## 9. Honest limitations

Worth stating plainly, because a viva panel will find them anyway:

- **The rule set is a proof of concept.** 22 rules is not comprehensive coverage of CAF and WAF; it is enough to demonstrate every pillar and validate the architecture.
- **The offline reasoner is heuristics, not reasoning.** It is a faithful control arm and a free default, but the genuine framework-intent reasoning is the LLM path.
- **Benchmark matching is by (resource, pillar), not exact rule id.** That is the fair test — was the violation surfaced to the developer? — but it is more lenient than exact matching, and the code says so.
- **The ground truth is self-authored.** 42 violations we seeded and labelled ourselves. A stronger evaluation would use an independent corpus such as public Terraform modules with known CVEs.
- **AWS and GCP coverage is thinner than Azure.** The architecture is cloud-agnostic and proven so by tests, but the rule *content* is Azure-weighted, matching the project's CAF/WAF framing.
- **`terraform plan` output can contain unknown values.** Attributes computed at apply time appear as `null`. Rules treat unknown as "not a violation" to avoid false positives, which means a small class of violations is invisible until apply. This is inherent to plan-time gating and is the accepted trade-off for catching things before they exist.
