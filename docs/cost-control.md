# Cost Control

The project runs on a fixed pool of student credits, so cost is treated as a design constraint rather than an afterthought. This document records every decision made for that reason — useful in the viva, because "why did you choose that resource?" is a question with a real answer here.

---

## The governing principle

> The gate must be free to run, so that it can run on every pull request.

If evaluating a PR cost money, teams would run the gate selectively, and a gate that runs selectively is not a gate. Everything below follows from that.

---

## What the pipeline costs

| Stage | Where it runs | Azure cost |
|---|---|---|
| Agent unit tests | GitHub-hosted runner | **₹0** |
| `terraform init` / `validate` | GitHub-hosted runner | **₹0** |
| `terraform plan` (seeded module, `-backend=false`) | GitHub-hosted runner | **₹0** — no Azure API call at all |
| `terraform plan` (demo module) | GitHub-hosted runner | **₹0** — read-only API calls are not billed |
| **The gate itself** | GitHub-hosted runner | **₹0** — pure Python over a local JSON file |
| PR comment + SARIF upload | GitHub | **₹0** |
| `terraform apply` | Azure | the demo footprint below |

GitHub Actions is free for public repositories and gives 2,000 minutes/month on free private ones. A full pipeline run takes about 90 seconds.

---

## What the deployed footprint costs

`infra/demo` contains exactly three billable-capable resources:

| Resource | SKU | Realistic monthly cost | Why this one |
|---|---|---|---|
| `azurerm_resource_group` | — | **₹0** | Free by definition |
| `azurerm_storage_account` | Standard, LRS/ZRS, Hot | **₹2–5** | Exercises 8 different CAF/WAF rules at a few megabytes of data |
| `azurerm_log_analytics_workspace` | PerGB2018, 0.1 GB/day cap | **₹0** | 5 GB/month is free; the cap makes overrun impossible |
| `azurerm_monitor_diagnostic_setting` | — | **₹0** | Configuration object, not a billed resource |

**Total: under ₹50/month, typically under ₹10.**

### What was deliberately left out

These are the resources that actually drain a student subscription. Each is demonstrated through plan-only fixtures instead — which exercise the gate identically, because the gate reads a plan and never touches the cloud.

| Resource | Would cost | How it is demonstrated instead |
|---|---|---|
| Virtual machine (`Standard_D8s_v3`) | ~₹25,000/month | Seeded in `examples/plans/azure_noncompliant.plan.json` |
| AKS cluster | ~₹8,000/month | Reasoning probes cover it; no cluster exists |
| SQL Server + database | ~₹4,000/month | Seeded fixture |
| App Service plan (P1v3) | ~₹6,000/month | Reasoning probes |
| Private endpoint | ~₹600/month each | `public_network_access = true` in the demo, with the gate flagging it as `CAF-LZ-002` — an honest, documented trade-off rather than a hidden one |
| Azure Firewall | ~₹40,000/month | Never created |

This is the single most important cost decision in the project: **the gate's input is a plan, not a deployment, so the most expensive misconfigurations can be tested at zero cost.** That is not a workaround — it is the reason gating at plan time is the right architecture.

---

## What the reasoning layer costs

| Mode | Cost per run | When it is used |
|---|---|---|
| `offline` (default) | **₹0** | Every CI run. Pinned via `SECOPS_REASONER: offline` in the workflow |
| `none` | **₹0** | Deterministic rules only |
| `azure_openai` with `gpt-4o-mini` | **< ₹0.10** | Opt-in, manual runs only |
| `azure_openai` with a large model | ₹2–5 | **Do not use.** No accuracy benefit here for 30× the cost |

Four mechanisms keep the LLM path cheap, implemented in `agent/reasoner/llm.py`:

1. **Triage** — only resources whose kind appears in the knowledge base are candidates; a bare resource group is never sent.
2. **Hard cap** — `max_resources: 12` in `policies/policy.yaml`. A 200-resource plan still sends 12.
3. **Redaction and truncation** — secrets are stripped, long strings truncated at 160 characters, lists capped at 5 elements. Prompt size is literally the bill.
4. **Disk cache** — keyed on a hash of model + prompt. Re-running an unchanged plan costs nothing, which matters because CI re-runs are common.

The offline reasoner recovers all 5 uplift violations in the benchmark, so **the paid path is a demonstration, not a dependency**.

---

## Guardrails

### 1. Budget alert
Created by the bootstrap at ₹500/month. If the portal API refuses (common on student subscriptions), set it manually: Cost Management → Budgets → Add. This is the safety net; do not skip it.

### 2. Log Analytics daily cap
`daily_quota_gb = 0.1`. When hit, ingestion **stops** rather than billing. Cheap resources with unbounded ingestion are the classic way a "free" workspace produces a surprise.

### 3. Approved-region list
`CAF-LZ-001` restricts deployments to `centralindia`, `southindia`, `eastus`. This is a governance control that doubles as a cost control — it prevents an accidental deployment into an expensive or distant region.

### 4. Terraform validation
`infra/demo/variables.tf` validates region and environment at plan time, so an invalid value fails before the gate even runs.

### 5. Session hygiene
```bash
bash scripts/azure-cost-check.sh   # before you start
bash scripts/azure-destroy.sh      # when you finish
```
`azure-cost-check.sh` specifically hunts for VMs, AKS clusters, SQL servers, App Service plans, Cognitive Services accounts, private endpoints, application gateways and firewalls — the eight resource types capable of doing real damage.

---

## Credit budget for the semester

| Phase | Activity | Estimated spend |
|---|---|---|
| Setup | Bootstrap, first deploy | ₹5 |
| Development | Storage + workspace running intermittently | ₹30/month |
| Review-2 demo | Deploy, demo, destroy | ₹5 |
| Optional LLM demo | ~200 gated runs on `gpt-4o-mini` | ₹20 |
| Review-3 demo | Deploy, demo, destroy | ₹5 |
| **Total for the project** | | **under ₹200 of a ₹8,000 grant** |

That leaves roughly 97% of the credits unspent, which is deliberate: it is headroom for the multi-cloud extension work, not slack.

---

## If something does go wrong

```bash
# 1. What exists right now?
bash scripts/azure-cost-check.sh

# 2. Kill everything the project created
bash scripts/azure-destroy.sh

# 3. Nuclear option -- delete every project resource group
az group list --query "[?tags.project=='agent-secops'].name" -o tsv \
  | xargs -I {} az group delete --name {} --yes --no-wait
```

Then check Cost Management → Cost analysis in the portal, filtered to the last 7 days and grouped by resource, to confirm the spend has stopped.
