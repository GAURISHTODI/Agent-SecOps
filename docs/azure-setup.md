# Connecting Azure

This is the only part of the project that spends anything. Follow it once, and the running cost stays under about ₹50/month — usually closer to ₹5.

---

## Before you start

| Requirement | Notes |
|---|---|
| Azure subscription with credits | Azure for Students gives $100 / ~₹8,000, valid 12 months |
| Azure CLI | `winget install Microsoft.AzureCLI` (Windows) or `brew install azure-cli` |
| Terraform ≥ 1.5 | `winget install HashiCorp.Terraform` |
| A GitHub repository | Public or private both work |

Verify:

```bash
az version
terraform version
az login
az account show --query "{name:name, id:id, state:state}" -o table
```

If `az account show` prints a subscription, you are ready. If you have more than one, pin the right one first:

```bash
az account set --subscription "Azure for Students"
```

---

## Step 1 — Run the bootstrap

```bash
bash scripts/azure-bootstrap.sh <your-github-org>/<your-repo>
```

On Windows, run this from Git Bash, or use WSL.

The script creates exactly five things, and deliberately nothing else:

| # | Resource | Cost | Why it is needed |
|---|---|---|---|
| 1 | Resource group `secops-tfstate-rg` | Free | Container for the state account |
| 2 | Storage account (Standard_LRS) | ~₹2/month | Terraform remote state; versioned, because losing state is unrecoverable |
| 3 | Entra ID app + federated credentials | Free | GitHub OIDC login — **no client secret is ever created or stored** |
| 4 | Role assignment, scoped to the resource groups | Free | Least privilege. A subscription-scoped grant would be flagged by our own `CAF-IAM-001` rule |
| 5 | Budget alert (default ₹500/month) | Free | The safety net on your credits |

### What OIDC federation means, and why it matters here

The usual approach is to create a service principal *secret* and paste it into GitHub. That secret is long-lived, copyable, and invisible to access reviews — exactly the pattern `WAF-SEC-006` and `CAF-IAM-001` exist to catch.

Instead, GitHub Actions presents a signed identity token describing the repo, branch and environment. Azure trusts that issuer for the specific subjects registered in step 3 and exchanges it for a token valid for minutes. Nothing long-lived is stored anywhere. The project holds itself to the standard it enforces on others — which is a good line to have ready in the viva.

---

## Step 2 — Configure GitHub

The bootstrap script prints these at the end.

**Settings → Secrets and variables → Actions → Secrets**

| Name | Value |
|---|---|
| `AZURE_CLIENT_ID` | The application (client) ID |
| `AZURE_TENANT_ID` | Your tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Your subscription ID |

**Settings → Secrets and variables → Actions → Variables**

| Name | Value |
|---|---|
| `TFSTATE_RG` | `secops-tfstate-rg` |
| `TFSTATE_SA` | The generated storage account name |

None of these are secrets in the dangerous sense — they are identifiers, not credentials. There is no password to leak.

**Settings → Environments → New environment → `production`**
Add yourself as a required reviewer. This gives a second, human control on top of the automated gate: even a passing gate waits for a click before anything is applied.

---

## Step 3 — First deploy

```bash
cd infra/demo
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars: set owner to your email

terraform init \
  -backend-config="resource_group_name=secops-tfstate-rg" \
  -backend-config="storage_account_name=<TFSTATE_SA>" \
  -backend-config="container_name=tfstate" \
  -backend-config="key=demo.tfstate"

terraform plan -out=tf.plan
terraform show -json tf.plan > plan.json

# The gate, run exactly as CI runs it
cd ../..
python -m agent.cli evaluate --plan infra/demo/plan.json --policy policies/policy.yaml
```

Only if that returns **PASS** should you apply:

```bash
cd infra/demo && terraform apply tf.plan
```

That ordering is the entire thesis of the project. Do it in that order during the demo, out loud.

---

## Step 4 — Verify the pipeline

Open a pull request that changes anything under `infra/`. You should see:

1. **Agent unit tests** run first — if the gate's own tests fail, its verdicts are meaningless, so nothing downstream runs.
2. **Two plan jobs in parallel**: the compliant module (must PASS) and the seeded module (must BLOCK). The seeded one *failing to be blocked* fails the build — that is the regression test for the gate itself.
3. **A compliance report comment** on the PR, updated in place on each push rather than spamming a new comment.
4. **Findings in the Security tab** via SARIF.

---

## Optional — Azure OpenAI for the LLM reasoning layer

**You do not need this.** The offline reasoner already recovers all 5 uplift violations in the benchmark, costs nothing, and is the CI default. Add Azure OpenAI only if you want to demonstrate genuine LLM reasoning in the viva.

```bash
# Cheapest possible configuration
az cognitiveservices account create \
  --name secops-openai \
  --resource-group secops-tfstate-rg \
  --location eastus \
  --kind OpenAI \
  --sku S0 \
  --yes

az cognitiveservices account deployment create \
  --name secops-openai \
  --resource-group secops-tfstate-rg \
  --deployment-name gpt-4o-mini \
  --model-name gpt-4o-mini \
  --model-version "2024-07-18" \
  --model-format OpenAI \
  --sku-name Standard \
  --sku-capacity 1          # 1K tokens/min -- a deliberate throttle
```

Then set locally, or as GitHub secrets:

```bash
export AZURE_OPENAI_ENDPOINT="https://secops-openai.openai.azure.com"
export AZURE_OPENAI_API_KEY="$(az cognitiveservices account keys list \
  --name secops-openai --resource-group secops-tfstate-rg --query key1 -o tsv)"
export AZURE_OPENAI_DEPLOYMENT="gpt-4o-mini"

python -m agent.cli evaluate \
  --plan examples/plans/azure_noncompliant.plan.json \
  --reasoner azure_openai
```

**Cost reality check.** `gpt-4o-mini` is roughly $0.15 per million input tokens. One gate run sends about 3–5K tokens after redaction and the 12-resource cap. That is well under ₹0.10 per run, and repeat runs on an unchanged plan hit the disk cache and cost nothing at all. Even so, `SECOPS_REASONER: offline` is pinned in the workflow environment so no PR can accidentally spend, and you must opt in per run.

Azure OpenAI access sometimes requires an application on student subscriptions. If you are not approved, nothing is lost — the agent falls back to the offline reasoner automatically and reports that it did so, rather than failing the build.

---

## Step 5 — Every session, without fail

```bash
# Before you start
bash scripts/azure-cost-check.sh

# When you are done
bash scripts/azure-destroy.sh
```

The demo footprint takes two minutes to recreate. There is no reason to leave it running between sessions, and a forgotten resource is the only realistic way this project could actually drain your credits.

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `AADSTS70021: No matching federated identity record` | The subject in the federated credential does not match the workflow. Check branch name and that `permissions: id-token: write` is present. |
| `Error acquiring the state lock` | A previous run died mid-apply. `terraform force-unlock <ID>` — read the message first. |
| `StorageAccountAlreadyTaken` | Storage names are globally unique. Re-run the bootstrap; it appends a random suffix. |
| `AuthorizationFailed` on apply | RBAC takes a few minutes to propagate. Wait, then retry. |
| Gate blocks your own compliant module | Read the report — it names the pillar and the fix. That is the gate working, not failing. |
| `az consumption budget create` fails (`Invalid budget configuration` or similar) | A known CLI-level bug on some subscription types (seen on Visual Studio Enterprise) — the underlying REST API is unaffected. Either use the portal (Cost Management → Budgets → Add), or call the API directly: `az rest --method put --uri "https://management.azure.com/subscriptions/<SUB_ID>/providers/Microsoft.Consumption/budgets/<NAME>?api-version=2023-05-01" --body @budget.json`, where `budget.json` has `properties.amount`, `properties.category: "Cost"`, `properties.timeGrain: "Monthly"`, `properties.timePeriod.startDate`, and `properties.notifications` with your threshold objects. Do not skip setting a budget either way. |
