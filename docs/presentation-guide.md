# Agent SecOps: Presentation Guide

Everything needed to explain, demonstrate and defend the project. Companion
documents: `docs/viva-guide.md` (algorithm and Q&A), `docs/knowledge-sources.md`
(what is Microsoft guidance and what is our own judgement).

---

## 0. About the red "Terraform apply" in GitHub Actions

It is **not a code failure**. In run `40477944568` the apply job started at
09:05 UTC and ended at 11:04 UTC with **zero steps executed**. It sat waiting
for the `production` environment approval for about two hours and was then
ended as failed. Azure was never touched.

Before presenting, either:
- click **Review deployments → Approve and deploy** within a minute or two of a push, or
- re-run the failed job and approve it.

Optional: change the workflow so apply only runs on a manual trigger
(`workflow_dispatch`), so ordinary pushes stay green.

---

## 1. In plain words (30 seconds)

Companies build cloud systems by writing a "recipe" (Terraform). A robot reads
the recipe and builds everything automatically. Before it builds, the robot
always prints a shopping list of what it is about to create. Nobody reads that
list.

Our agent is a **security guard who reads that list**. It checks it against
Microsoft's two rulebooks for building cloud systems responsibly. If something
is unsafe, such as a storage account open to the whole internet, it **stops the
build before anything exists**. The mistake never costs money and never
exposes data.

---

## 2. Where it sits (process flow)

```
Developer pushes Terraform  ->  GitHub Actions starts
   -> terraform plan   (real, about 5-20 s)  -> plan.json  (the shopping list)
   -> AGENT SECOPS GATE (about 20 ms)        -> PASS / REMEDIATE / BLOCK
        BLOCK  -> report on the PR, nothing built, Azure unchanged
        PASS   -> human approves -> terraform apply -> resource appears
```

Why at the plan: it is the earliest moment the real list is known (variables,
modules and loops resolved) and the last moment stopping is free. Scanning
`.tf` files sees unresolved variables; scanning after apply is too late.

---

## 3. Inside the gate (end-to-end pipeline)

| Step | What happens |
|---|---|
| 1. Parse and normalise | Azure, AWS and GCP resource types become canonical kinds (`object_storage`, `network_firewall`, ...). One rule then works on all three clouds. |
| 2. Layer 1: rules | 22 deterministic rules, each with a pillar, severity, rationale and ready-made fix. Confidence 1.0. |
| 3. Layer 2: reasoning | Retrieves the guidance for that resource kind and looks for intent violations no rule covers. Output is verified: it cannot invent resources, cannot repeat rule findings, drops low confidence. Advisory by default. |
| 4. Layer 3: policy | Severity thresholds, per-rule overrides, waivers that expire. |
| 5. Output | Exit code 0/1/2/3 is the decision. Also Markdown (PR comment), JSON, SARIF (GitHub Security tab) and the dashboard. |

### Reasoning layer algorithm

1. **Retrieve**: look up the resource kind in the knowledge base to get relevant pillars and a watch-for list (a type lookup, so deterministic and auditable).
2. **Deduplicate**: drop anything the rules already reported.
3. **Judge**: offline heuristic probes (default, free) or an LLM prompted with the retrieved guidance (temperature 0, JSON only, cached by prompt hash).
4. **Verify**: drop findings on resources not in the plan, below confidence 0.6, or with unknown pillar/severity.
5. **Govern**: findings are advisory unless the organisation sets `fail_on_reasoner_findings`.

---

## 3b. Novelty (state it honestly)

- A **hybrid gate at a new insertion point**: rules plus reasoning on the resolved plan, before apply. Checkov, tfsec and OPA are rules only.
- **Retrieval keyed on resource type**, not embeddings: deterministic, auditable, cheap.
- **Safe use of an unreliable component on a control path** (the four guardrails). This is the engineering contribution.
- **A measurable ablation**: 37/42 with rules alone, 42/42 with reasoning, 0 false positives.
- **There is no trained model, by design**: no labelled data exists, and a build gate must be explainable.
- **Volunteer this:** the 42 labels were written by the same team as the rules, so 100% is a regression result, not independent accuracy. The LLM path is built but not benchmarked.

---

## 4. Why the dashboard looks "pre-processed", and the true answer

The gate step itself genuinely takes about **20 ms**. The slow part
(`terraform plan`, 5-20 s) happens *before* the gate. Files in `examples/plans`
are plans that were already generated, so loading one skips that slow stage.
Nothing is faked, but it looks that way. Azure shows nothing for the same
reason: **blocking means nothing gets created**. The proof is that the bad
resources are absent.

---

## 5. The demo that proves it (follow in this order)

Keep an Azure portal tab on `secops-dev-cin-rg` open from the start.

1. **Show the problem.** Open `examples/terraform/aws_noncompliant/main.tf`; read three bad lines (public ACL, SSH open to `0.0.0.0/0`, plaintext password).
2. **Dashboard -> "Run the real pipeline" -> `aws_noncompliant`.** Real `terraform init -> plan -> show` runs, then the gate: BLOCK, 21 findings. The "Real pipeline run" panel shows actual Terraform output.
3. **Edit live.** In that file set `acl = "private"` and `region = "ap-south-1"`, run again. Findings drop on the spot; read the new number from the screen.
4. **The Azure side.** In the portal, search for the bad resources: they do not exist. "Blocked before creation: zero cost, zero exposure."
5. **GitHub, the real flow.** Open a pull request that adds an insecure storage account to `infra/demo`. Watch CI run live, the red gate job, and the bot comment with findings and fixes. Azure is still unchanged. Push the suggested fix, watch it go green, approve the apply.
6. **Close.** Dashboard -> Benchmark tab, then state the limits (section 6).

> **Dry-run step 5 tonight.** Every CI run so far was a push to `main`; the
> pull-request path (PR comment, `pull_request` OIDC credential) has never been
> exercised end to end.

Dashboard URL shortcuts for a clean start:
`/?plan=team_demo.plan.json`, `/?tab=benchmark`, `/?run=aws_noncompliant`,
`&reasoning=off`, `&theme=light`.

Demo resources used in scripts: `gaurish_s_resourceA` (Azure storage),
`akshat_s_resourceB` (AWS bucket), `bhumika_s_resourceC` (GCP firewall), from
`examples/plans/team_demo.plan.json` (BLOCK, 14 findings: 12 rules, 2 reasoning).

---

## 6. Is the project finished? Honest status

**Done and working**
- 22 rules, parser, reasoning layer, policy layer, CLI, reports.
- Dashboard with real Terraform runs and PDF download.
- 69 passing tests; benchmark 37/42 -> 42/42, 0 false positives.
- CI that blocks bad plans; live Azure deployment (about 4 rupees/month).
- Knowledge audit against Microsoft docs; report and deck.

**Not finished or not proven**
- **Recent work is not pushed.** The knowledge-audit fixes, dashboard v2, PDF download and docs exist only on the laptop; GitHub runs older code. Commit and push before the demo.
- **Pull-request path untested** (see section 5).
- **Apply job has not completed in a recent run** (approval timeout, section 0).
- **LLM reasoner never run against a real model** or benchmarked. Everything demonstrable uses the offline heuristics.
- **Benchmark is not independent** (labels written by the authors).
- **Only Azure is truly deployed.** AWS and GCP are plan-only.
- **Real AWS/GCP coverage is thinner.** The reasoner found nothing on real AWS and GCP plans; the diagnostics check matches by name.
- **22 rules are a small slice of CAF/WAF**, which is why the reasoning layer exists.
- **Report and deck open items:** Turnitin plagiarism and AI scores, the guide's approval mail (slide 2), HoD title, signatures, and text issues awaiting a decision.
- **Live Azure resources remain deployed.** Run `terraform destroy` after the demo.

---

## 7. Likely questions

| Question | Answer |
|---|---|
| Where is the ML? | None, by design. Retrieval plus verification, measured by ablation. |
| How is it different from Checkov? | Checkov only enforces rules someone wrote. We add reasoning for unwritten guidance, with guardrails. |
| Can the model wrongly block a release? | No. Reasoner findings are advisory unless the organisation opts in. |
| Why is the gate so fast? | It is a pure function over JSON; the cost is Terraform, not the gate. |
| Does CAF apply to AWS and GCP? | Microsoft wrote it for Azure. We extend the intent to equivalent resources, and the report says so. |
| Is 100% real? | It is a regression suite written by us; independent evaluation is future work. |

---

## 8. Checklist before tomorrow

- [ ] Commit and push all local changes.
- [ ] Dry-run the pull-request demo (section 5, step 5).
- [ ] Restart the dashboard server (`python -m dashboard.server`) so it serves the latest code.
- [ ] Approve (or re-run) the apply job so the pipeline shows green.
- [ ] Open the Azure portal tab and the GitHub Actions tab in advance.
- [ ] Run Turnitin on the report; paste the guide's approval mail into slide 2.
- [ ] Take final screenshots: Actions run after approval, a real PR with the bot comment.

---

## 9. Dashboard additions (latest)

- **Presentation pacing** (switch next to "Reasoning layer", on by default). The
  display steps through Parse -> Layer 1 -> Layer 2 -> Layer 2b -> Layer 3 ->
  Verdict at about one second each (about 7-8 s in total) so each stage can be
  explained. The banner says the display is slowed, shows the engine's real time
  (tens of milliseconds) and reveals each stage's measured time as it completes.
  Turn it off (or use `?pace=off`) to see the true speed. **Say this out loud:**
  the algorithm is fast; the pacing is for explanation. Do not claim it is
  compute time.
- **Terraform lookup.** The dashboard now finds Terraform even when the terminal's
  PATH is stale (winget, Chocolatey, Program Files), or from `SECOPS_TERRAFORM`.
  If you installed Terraform after opening the terminal, you no longer need to
  reopen it; restart `python -m dashboard.server`.

- **Dependency graph visualisation.** In the Gate tab, after the Processing trace, click
  **"Show dependency graph"**. A radar-style canvas shows the resources as glowing nodes
  (size = asset value, ring colour = risk, flame/bucket/database icons by kind) joined by
  Terraform references. The dangerous path pulses red with moving particles.
  **"Simulate exposure spread"** replays the algorithm step by step: step 1 exposure sources
  ignite, each next step shows the decayed exposure reaching the next hop, and the final step
  shows every node's risk score. Click a node for its numbers (exposure, weakness, asset,
  risk, risk alone). Works on real plans (use "Run the real pipeline"); hand-written
  fixtures have no links, so the panel says so.
  A red ring is high risk on its own; only the pulsing alarm ring is a graph-found compound
  path. URL switches for a clean start: `?graph=open`, `&gstep=N` (freeze at a simulation step).
