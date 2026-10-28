# Viva and demo guide

Everything needed to explain and demonstrate Agent SecOps. Read
`docs/knowledge-sources.md` first: it lists what is Microsoft guidance and what
is this project's own judgement, so you never overclaim.

---

## 1. Explaining the project

### 1.1 Layman version (30 seconds)

Companies describe their cloud setup in a text file (a "recipe"), and a robot
builds it automatically. Before the robot builds anything, the full shopping
list is known. Our agent is a security guard standing at that exact moment. It
reads the list and checks it against Microsoft's rulebooks for building
responsibly: is it labelled, in the right country, locked down, backed up,
not open to the whole internet? If the list breaks the rules, the guard stops
the build. Nothing gets created, so no security hole exists and no money is spent.

### 1.2 Technical version (2 minutes)

A GitHub Actions job runs `terraform plan`, exports it with
`terraform show -json`, and runs our CLI between plan and apply. The CLI:

1. **Parses** `resource_changes[]` into cloud-agnostic `Resource` objects with a
   canonical `Kind` (`azurerm_storage_account`, `aws_s3_bucket` and
   `google_storage_bucket` all become `object_storage`). This one mapping is the
   whole multi-cloud story.
2. **Layer 1:** 22 deterministic rules, each tagged with a framework pillar,
   severity and a written rationale. Confidence 1.0.
3. **Layer 2a, organisational customized policies:** checks for intent that no rule
   encodes (section 2); **Layer 2b** adds dependency-graph risk.
4. **Layer 3, thresholds & waivers:** severity thresholds, per-rule overrides,
   and time-boxed waivers that expire.
5. Returns **pass / remediate / block** as the process exit code (0 / 1 / 2),
   plus Markdown, JSON and SARIF reports.

Why at the plan: it is the earliest point where variables, modules and
`for_each` are resolved, and the last point before anything exists.

---

## 2. The reasoning layer: algorithm, core logic, novelty

### 2.1 The problem it solves

Rules only catch what someone already wrote down. CAF/WAF are mostly narrative
guidance ("data tier should default-deny", "production data must be
recoverable"). Turning every sentence into a rule is endless work. Layer 2 asks
the question a human reviewer asks: *given the guidance for this kind of
resource, does this configuration violate its intent in a way no rule covers?*

### 2.2 The algorithm

```
REASON(resources R, already_reported A):
  for each resource r in R:
    1. RETRIEVE   focus = KB.kind_focus[r.kind]          # pillars + watch_for list
                  guidance = KB.pillars[focus.pillars].principles
    2. DEDUPLICATE skip anything whose title is in A[r.address]
    3. JUDGE      offline: for each probe p with r.kind in p.kinds,
                           p.pillar in focus.pillars, p.confidence >= min:
                           if p.test(r): emit finding(p)
                  llm:     prompt = system_rules + {redact(r), guidance, A}
                           reply  = model(prompt, temperature=0, JSON only)
                           (cached by sha256(model + prompt); max N resources)
    4. VERIFY     drop findings whose address is not in R      (no invented resources)
                  drop findings below min_confidence           (no weak guesses)
                  coerce unknown pillar/severity to safe values (no crash)
    5. GOVERN     Layer 3 treats reasoner findings as advisory unless
                  policy.fail_on_reasoner_findings = true
```

Core logic in one sentence: **retrieve only the relevant framework guidance for
this resource kind, ask for violations of its intent that the rules did not
already report, then verify the answer mechanically before it can influence a
build.**

### 2.3 Two interchangeable reasoners

| | Offline reasoner | LLM reasoner |
|---|---|---|
| What it is | 12 hand-written probes, each mapped to a KB `watch_for` line | Azure OpenAI / Anthropic over plain `urllib`, prompted with retrieved guidance |
| Cost | Free, milliseconds, deterministic | Pennies; capped resources, capped tokens, disk cache |
| Role | CI default and the **control arm** of the experiment | The optional extension |
| Failure | Cannot fail | Endpoint down becomes an info finding; the gate never breaks |

### 2.4 Novelty (what to tell faculty)

Be precise; do not claim "we trained an AI". The defensible contributions are:

1. **Hybrid neuro-symbolic gate at a new insertion point.** Deterministic rules
   for known violations plus knowledge-grounded reasoning for unencoded intent,
   applied to the resolved plan, before apply. Existing tools (Checkov, tfsec,
   OPA, Sentinel) are rules only.
2. **Retrieval keyed on a type system, not embeddings.** Retrieval is a lookup
   on a canonical resource kind, so it is deterministic, auditable and tiny
   (which is also why it is cheap). The multi-cloud claim rides on this.
3. **Safe use of an unreliable component on a control path.** Four guardrails:
   cannot invent resources, cannot duplicate Layer 1, cannot block by default,
   cannot break the pipeline. This is the engineering contribution.
4. **A measurable ablation.** Rules-only vs rules+reasoning on the same plans
   isolates what reasoning adds (33/42 -> 42/42, 9 recovered, 0 false positives).
5. **Governance as code.** Expiring waivers so exceptions cannot become permanent.

### 2.5 "Where is the ML / training?"

Say this directly: *there is no trained model, by design.* There is no labelled
corpus of compliant vs non-compliant plans to train on, a build gate must be
deterministic and explainable, and a pretrained LLM given retrieved guidance
(retrieval-augmented generation) avoids training entirely. The "method" is
RAG + schema-constrained output + mechanical verification, evaluated by
ablation. Stronger evidence if they push: the weaknesses below.

### 2.6 Honest weaknesses (volunteer these)

- The benchmark ground truth was written by the same authors as the rules and
  probes, so 100% is a regression suite, not independent accuracy.
- The 9 "recovered by reasoning" come from the offline heuristics. The LLM path
  is implemented and guard-railed but has **not** been benchmarked.
- Future work that answers this: run both reasoners on an independent set
  (public vulnerable-Terraform repos such as TerraGoat), report precision and
  recall, and compare against Checkov as a baseline.

---

## 3. Demo script: all cases, step by step

Use the three named resources throughout:

| Name | Cloud | What is wrong |
|---|---|---|
| `gaurish_s_resourceA` | Azure storage account | TLS 1.0, anonymous access, LRS in prod, public network, shared keys |
| `akshat_s_resourceB` | AWS S3 bucket | public-read ACL, unapproved region `sa-east-1`, no versioning, missing tags |
| `bhumika_s_resourceC` | GCP firewall | SSH open to `0.0.0.0/0` |

Fixture: `examples/plans/team_demo.plan.json`. Expected verdict: **BLOCK**.
Read the exact finding counts off the screen; do not recite numbers from memory.

### Setup (before the room fills)

```powershell
pip install -r requirements.txt
python -m pytest tests -q                 # expect all passing
python -m dashboard.server                # opens http://localhost:8000
```
Keep a terminal at the repo root and the GitHub Actions tab open.

### Case 0: the idea (Gaurish, 1 min)
Show `docs/figures/fig2_architecture.png`. Give the layman version (1.1).

### Case 1: a clean plan passes (Bhumika)
Dashboard, Plan = *Azure - compliant workload*. Point at: green **PASS**,
exit code 0, 0 findings, the **Processing trace** with real millisecond timings,
and the SHA-256 chip proving which bytes were judged.
CLI equivalent: `python -m agent.cli evaluate --plan examples/plans/azure_compliant.plan.json; echo $LASTEXITCODE`

### Case 2: three resources, three clouds, one gate (all three)
Plan = *Team demo*. Say: "Gaurish's Azure storage, Akshat's AWS bucket and
Bhumika's GCP firewall go through one engine." Scroll to **Resources parsed**:
show the three different cloud types collapse to canonical kinds
(`object_storage`, `object_storage`, `network_firewall`). Then expand each
finding group and read one fix per resource.

### Case 3: what the reasoning layer adds (Gaurish)
Toggle **Reasoning layer** off, then on. The Layer split bar gains an orange
segment, and findings tagged *reasoning* appear (for example shared keys left
enabled on resourceA, versioning off on resourceB). Explain section 2.2 using
the trace: Layer 2 is a separate, timed stage.

### Case 4: bring your own plan (Akshat)
1. Click **Upload plan.json** and choose `examples/plans/aws_noncompliant.plan.json`,
   or drag the file onto the page, or use **Paste JSON**.
2. The Plan dropdown now shows the file name, the SHA-256 and timestamp change.
3. Toggle the reasoning layer: the *uploaded* plan is re-evaluated (it is no
   longer swapped for a built-in one).
Say: "Any `terraform show -json` output works, from any cloud."

### Case 5: the real pipeline, not a fixture (Bhumika)
In the **Run the real pipeline** bar choose `examples/terraform/aws_noncompliant`
and click **terraform plan -> gate**. About 7 seconds (first run downloads the
provider). The **Real pipeline run** panel shows the actual `terraform init`,
`plan` and `show -json` output, then the gate verdict. Repeat with
`gcp_noncompliant`. `noncompliant` (Azure) takes about 20 s and needs your
`az login`.
Say: "No cloud account, no cost: dummy credentials, plan only, never apply."

### Case 6: download the report (anyone)
Use **Download report**: **PDF** (opens a print view; choose *Save as PDF*),
**JSON**, **Markdown** (the PR comment), **SARIF** (GitHub Security tab).

### Case 7: the same thing in CI (Bhumika)
Open the Actions tab on the latest run. Show: unit tests green; four seeded or
compliant matrix jobs green (green on a seeded job means *correctly blocked*);
the uploaded `gate-report-*` artifacts; the `production` approval before apply.
Optional live PR: change `min_tls_version` on `infra/demo/main.tf` line 103 from
`"TLS1_2"` to `"TLS1_0"`, open a PR, show the bot comment and the red job, then revert.

### Case 8: real Azure (Bhumika, last)
`az resource list -g secops-dev-cin-rg -o table`. Say: "This was gated before it
was applied; steady cost is a few rupees a month; `terraform destroy` returns it
to zero."

### Case 9: the evidence (Gaurish)
Dashboard **Benchmark** tab: 42 seeded violations, rules alone 33, with
reasoning 42, 0 false positives. Then volunteer section 2.6 before they ask.

---

## 4. Likely questions

- **Is it trained?** No; RAG plus verification, by design (2.5).
- **Why not just Checkov?** Rules only; cannot judge unencoded intent, and does not
  keep the reasoner advisory-by-default with guardrails.
- **Can the LLM wrongly block a deploy?** No: advisory unless the org opts in.
- **Does CAF/WAF apply to AWS/GCP?** Microsoft wrote them for Azure; we
  extrapolate their intent to equivalent resources (`docs/knowledge-sources.md`).
- **Is 100% real?** It is a regression suite written by us; independent
  evaluation is future work.
