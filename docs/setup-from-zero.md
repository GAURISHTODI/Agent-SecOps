# Setup From Zero

Everything from an empty machine to a working Azure-connected pipeline, done manually. No scripts — every step is a command or a portal click you can explain in a viva.

**Read this first, so the "frontend/backend" question is settled.** The *product* here is a command-line program that runs inside a CI/CD pipeline — in the real workflow, the gate is a CLI whose **exit code** decides whether `terraform apply` runs. There is no web app in that path.

On top of that we also ship a **local dashboard** purely for demonstrating the project (Part 1.5). It is a React frontend served by a small Python backend, and it drives the exact same engine the CLI does. Use it in the review; use the CLI in the pipeline.

Part 1 and Part 1.5 need no cloud account at all.

---

## Map of what you are about to do

| Part | What | Time | Needs Azure? |
|---|---|---|---|
| 1 | Install tools and run the agent locally | 10 min | No |
| 2 | Put the project on GitHub | 10 min | No |
| 3 | Set up Azure manually (minimal resources) | 25 min | Yes |
| 4 | Connect GitHub to Azure | 10 min | Yes |
| 5 | Deploy once from your laptop | 10 min | Yes |
| 6 | Run the pipeline end to end | 10 min | Yes |
| 7 | Tear down | 2 min | Yes |

Total Azure spend if you follow this exactly: **under ₹10.**

---

# Part 1 — Install tools and run the agent locally

You can do all of Part 1 with no Azure account and no GitHub account.

## 1.1 Install the tools

Open **PowerShell as Administrator** and run:

```powershell
winget install Python.Python.3.11
winget install Git.Git
winget install Microsoft.AzureCLI
winget install HashiCorp.Terraform
```

Close PowerShell and open a **new** one (so the PATH updates), then verify:

```powershell
python --version      # Python 3.11.x  (3.9+ is fine)
git --version         # git version 2.x
az version            # azure-cli 2.x
terraform version     # Terraform v1.9.x
```

If `python` opens the Microsoft Store instead of running, disable the alias: Settings → Apps → Advanced app settings → App execution aliases → turn off both `python.exe` entries.

## 1.2 Install the project's Python dependencies

```powershell
cd "d:\Code\SecOps Agent for CAFWAF compliant Cloud Deployments in CICD"
pip install -r requirements.txt
```

That installs exactly two packages: PyYAML and pytest.

## 1.3 Run the agent — this is "running the project"

```powershell
# The compliant plan -- should PASS
python -m agent.cli evaluate --plan examples/plans/azure_compliant.plan.json

# The seeded misconfigurations -- should BLOCK
python -m agent.cli evaluate --plan examples/plans/azure_noncompliant.plan.json
```

Check the exit code, because **the exit code is the gate** — it is how the pipeline decides whether to deploy:

```powershell
python -m agent.cli evaluate --plan examples/plans/azure_compliant.plan.json
echo $LASTEXITCODE      # 0 = pass

python -m agent.cli evaluate --plan examples/plans/azure_noncompliant.plan.json
echo $LASTEXITCODE      # 2 = block
```

## 1.4 The rest of the local surface

```powershell
python -m pytest tests/ -q                    # 63 tests
python -m agent.cli rules                     # the 22-rule catalogue
python -m agent.cli explain WAF-SEC-004       # why one rule exists
python scripts/benchmark.py                   # detection + false-positive numbers
```

To see the report a developer actually gets on a pull request:

```powershell
python -m agent.cli evaluate `
  --plan examples/plans/azure_noncompliant.plan.json `
  --markdown out/report.md
```

Then open `out/report.md` in VS Code and press `Ctrl+Shift+V` to preview it.

**At this point the gate is fully working.**

---

# Part 1.5 — Run the dashboard (the visual demo)

This is what you put on the projector.

```powershell
python -m dashboard.server
```

That is the whole command. It starts a small backend on `http://localhost:8000` and opens your browser automatically. To stop it, press `Ctrl+C`.

If port 8000 is busy: `python -m dashboard.server --port 8001`
To stop it opening a browser: `python -m dashboard.server --no-browser`

## What the two halves are

| Half | What it is | Where |
|---|---|---|
| **Backend** | Python HTTP server wrapping the gate engine. Endpoints: `/api/plans`, `/api/evaluate`, `/api/benchmark`, `/api/rules` | `dashboard/server.py` |
| **Frontend** | React app — verdict banner, stat tiles, charts, expandable findings | `dashboard/static/` |

There is **no `npm install` and no build step**. React is loaded from a CDN and JSX is compiled in the browser. That is a deliberate choice for a college demo: one command, no `node_modules`, nothing to break on a strange machine. (A production app would use Vite and compile ahead of time — worth saying if you are asked.)

The frontend needs an internet connection **the first time it loads**, to fetch React from the CDN. After that the browser caches it. If the CDN is unreachable the page tells you so and points you at the CLI, rather than showing a blank screen.

## The three tabs

**Gate** — pick a plan from the dropdown and see the verdict banner (PASS/REMEDIATE/BLOCK with its exit code), stat tiles, a bar chart of violations by CAF/WAF pillar, one by severity, and every finding grouped by resource with a copy-pasteable Terraform fix.

**Benchmark** — runs the detection benchmark live: 42 seeded violations, rules-only vs rules-plus-reasoning, per plan, with the false-positive count.

**Rules** — all 22 rules with the framework rationale for each.

## The demo sequence that lands

1. Select **"Azure — compliant workload"** → green **PASS**, exit code 0, no findings.
2. Select **"Azure — seeded misconfigurations"** → red **BLOCK**, exit code 2, 48 findings across 9 pillars.
3. **Toggle "Reasoning layer" off.** Watch the orange segment vanish from the "Which layer found what" chart and the reasoning findings disappear from the list. Turn it back on and they return.
   > *"Everything orange is a violation that no hand-written rule catches. That is the contribution of this project, and you are watching it appear and disappear."*
4. Switch to **AWS** and then **GCP** — same rules, same verdict logic, different cloud.
5. Open the **Benchmark** tab: 88.1% with rules alone, 100% with reasoning, zero false positives.

Step 3 is the moment worth rehearsing.

Everything below is about connecting the project to real infrastructure.

---

# Part 2 — Put the project on GitHub

## 2.1 Create a GitHub account

If you do not have one, sign up at [github.com](https://github.com). Then apply for the **GitHub Student Developer Pack** at [education.github.com/pack](https://education.github.com/pack) with your VIT email — it gives free private repository Actions minutes, which is useful.

## 2.2 Initialise the repository locally

```powershell
cd "d:\Code\SecOps Agent for CAFWAF compliant Cloud Deployments in CICD"

git init
git branch -M main

# Tell git who you are (once per machine)
git config user.name "Gaurish Todi"
git config user.email "gaurishtodi@gmail.com"
```

Check what git will commit. The `.gitignore` already excludes state files, plan output, caches and the LLM cache:

```powershell
git status
```

The two PDFs will show up. Keep them — they are your project documentation. If you would rather not commit them:

```powershell
Add-Content .gitignore "`n# Review PDFs`n*.pdf"
```

Now commit:

```powershell
git add .
git commit -m "Agent SecOps: CAF/WAF compliance gate for Terraform in CI/CD"
```

## 2.3 Create the GitHub repository

**Option A — in the browser (recommended if you are new to this):**

1. Go to [github.com/new](https://github.com/new)
2. **Repository name:** `agent-secops`
3. **Description:** `AI SecOps agent gating Terraform deployments against Azure CAF/WAF in CI/CD`
4. Choose **Public** (free unlimited Actions minutes) or **Private** (2,000 min/month free)
5. **Do NOT** tick "Add a README", "Add .gitignore" or "Choose a license" — you already have files, and those would create a conflict
6. Click **Create repository**

GitHub then shows you a URL. Use it:

```powershell
git remote add origin https://github.com/<your-username>/agent-secops.git
git push -u origin main
```

The first push will ask you to sign in — a browser window opens, approve it.

**Option B — with the GitHub CLI:**

```powershell
winget install GitHub.cli
gh auth login          # choose GitHub.com -> HTTPS -> login with browser
gh repo create agent-secops --public --source=. --remote=origin --push
```

## 2.4 Confirm the workflow is there

Open your repo in the browser and click the **Actions** tab. You should see the **SecOps Gate** workflow listed. It may have already run on your push and **failed at the Azure login step** — that is expected and correct, because you have not connected Azure yet. That is Part 3.

---

# Part 3 — Set up Azure manually

Everything here is free or costs a few rupees. I will give you both the portal clicks and the CLI command for each step; use whichever you prefer, they do the same thing.

## 3.1 Get a subscription with credits

1. Go to [azure.microsoft.com/free/students](https://azure.microsoft.com/free/students)
2. Sign in with your **VIT email** (`@vitstudent.ac.in`)
3. Verify your student status — you get **$100 credit, valid 12 months, no credit card required**

Then log in from your terminal:

```powershell
az login
```

A browser opens; sign in with the same account. Then confirm:

```powershell
az account show --output table
```

If you have more than one subscription, pick the student one:

```powershell
az account list --output table
az account set --subscription "Azure for Students"
```

**Write down your Subscription ID and Tenant ID now — you need them in Part 4:**

```powershell
az account show --query "{subscriptionId:id, tenantId:tenantId}" --output table
```

## 3.2 Create the resource groups

You need two. Resource groups are **free** — they are just containers.

| Name | Purpose |
|---|---|
| `secops-tfstate-rg` | Holds the Terraform state storage account |
| `secops-dev-cin-rg` | Holds the demo workload |

**Portal:** Home → Resource groups → **+ Create** → Subscription: your student one → Name → Region: **Central India** → Next: Tags → add `owner`, `environment`, `costcenter`, `project` → Review + create.

**CLI (faster):**

```powershell
az group create --name secops-tfstate-rg --location centralindia `
  --tags owner=gaurishtodi@gmail.com environment=prod costcenter=CC-1042 project=agent-secops

az group create --name secops-dev-cin-rg --location centralindia `
  --tags owner=gaurishtodi@gmail.com environment=dev costcenter=CC-1042 project=agent-secops
```

The `project=agent-secops` tag matters — the cost-check and destroy scripts find resources by it.

> **Why `centralindia`?** It is on the approved list in `policies/policy.yaml` (rule `CAF-LZ-001`), it is the closest region to you, and it is cheap. If you deploy elsewhere the gate will block you — which is the rule working.

## 3.3 Create the Terraform state storage account

Terraform needs somewhere to store state. State files are kilobytes, so this costs roughly **₹2/month**.

Storage account names must be **globally unique across all of Azure**, 3–24 characters, lowercase letters and digits only. Pick something with a random suffix:

```powershell
$SA = "secopstfstate" + (Get-Random -Minimum 1000 -Maximum 9999)
echo $SA        # write this down -- you need it in Part 4
```

**Portal:** Home → Storage accounts → **+ Create**
- Resource group: `secops-tfstate-rg`
- Storage account name: your generated name
- Region: **Central India**
- Performance: **Standard** ← not Premium
- Redundancy: **Locally-redundant storage (LRS)** ← the cheapest option
- **Advanced tab:** Require secure transfer = **Enabled**, Minimum TLS version = **1.2**, Allow blob anonymous access = **Disabled**
- Review + create

**CLI:**

```powershell
az storage account create `
  --name $SA `
  --resource-group secops-tfstate-rg `
  --location centralindia `
  --sku Standard_LRS `
  --kind StorageV2 `
  --min-tls-version TLS1_2 `
  --https-only true `
  --allow-blob-public-access false `
  --tags owner=gaurishtodi@gmail.com environment=prod costcenter=CC-1042 project=agent-secops
```

Now create the container that holds the state file. **Portal:** open the storage account → Data storage → Containers → **+ Container** → Name `tfstate` → Anonymous access level: **Private** → Create.

**CLI:**

```powershell
az storage container create --name tfstate --account-name $SA --auth-mode login
```

If that errors with a permissions message, wait two minutes for RBAC to propagate and retry, or add yourself as **Storage Blob Data Contributor** on the storage account (Access control (IAM) → Add role assignment).

Enable versioning — losing Terraform state is unrecoverable, so this is worth the zero rupees it costs:

```powershell
az storage account blob-service-properties update `
  --account-name $SA --resource-group secops-tfstate-rg --enable-versioning true
```

## 3.4 Create the app registration for GitHub

This is how GitHub Actions will authenticate to Azure. Read this bit carefully — it is the part most people get wrong, and it is also the most interesting thing to explain in your viva.

**The normal approach is to create a client secret and paste it into GitHub.** That secret is long-lived, copyable, and invisible to access reviews. It is exactly the pattern your own `WAF-SEC-006` and `CAF-IAM-001` rules exist to catch. **We are not going to do that.**

Instead we use **OIDC federation**: GitHub presents a signed token that says "I am a workflow in repo X on branch main", Azure trusts that issuer for specific registered subjects, and hands back a token valid for a few minutes. **No secret is ever created or stored.**

### 3.4.1 Register the application

**Portal:** Home → **Microsoft Entra ID** → App registrations → **+ New registration**
- Name: `secops-github-oidc`
- Supported account types: **Accounts in this organizational directory only**
- Redirect URI: leave blank
- Register

On the overview page, **copy the Application (client) ID** — you need it in Part 4.

**CLI:**

```powershell
$APP_ID = az ad app create --display-name "secops-github-oidc" --query appId -o tsv
echo $APP_ID        # write this down

# Create the service principal (the identity that actually gets permissions)
az ad sp create --id $APP_ID
```

### 3.4.2 Add the federated credentials

You need **three**, one per situation the workflow runs in. Replace `<OWNER>/<REPO>` with your real repo, for example `gaurishtodi/agent-secops`.

**Portal:** your app registration → **Certificates & secrets** → **Federated credentials** tab → **+ Add credential**
- Federated credential scenario: **GitHub Actions deploying Azure resources**
- Organization: your GitHub username
- Repository: `agent-secops`
- Then add one credential for each **Entity type**:

| # | Entity type | Value | Name |
|---|---|---|---|
| 1 | Branch | `main` | `gh-main` |
| 2 | Pull request | — | `gh-pr` |
| 3 | Environment | `production` | `gh-env-production` |

**CLI (do all three at once):**

```powershell
$REPO = "<OWNER>/agent-secops"      # <-- edit this

az ad app federated-credential create --id $APP_ID --parameters "{
  'name': 'gh-main',
  'issuer': 'https://token.actions.githubusercontent.com',
  'subject': 'repo:$REPO`:ref:refs/heads/main',
  'audiences': ['api://AzureADTokenExchange']
}".Replace("'", '"')

az ad app federated-credential create --id $APP_ID --parameters "{
  'name': 'gh-pr',
  'issuer': 'https://token.actions.githubusercontent.com',
  'subject': 'repo:$REPO`:pull_request',
  'audiences': ['api://AzureADTokenExchange']
}".Replace("'", '"')

az ad app federated-credential create --id $APP_ID --parameters "{
  'name': 'gh-env-production',
  'issuer': 'https://token.actions.githubusercontent.com',
  'subject': 'repo:$REPO`:environment:production',
  'audiences': ['api://AzureADTokenExchange']
}".Replace("'", '"')
```

> The backtick before `:` in `$REPO\`:ref:` is PowerShell escaping — without it PowerShell tries to read `$REPO:ref` as one variable name. If this fights you, use the portal instead; it is genuinely easier for this step.

Verify all three exist:

```powershell
az ad app federated-credential list --id $APP_ID --query "[].{name:name, subject:subject}" -o table
```

### 3.4.3 Grant permissions — scoped, not subscription-wide

**Portal:** each resource group → **Access control (IAM)** → **+ Add** → Add role assignment → Role: **Contributor** → Members: **User, group, or service principal** → Select members → search `secops-github-oidc` → Review + assign. Do this on **both** resource groups.

**CLI:**

```powershell
$SP_ID = az ad sp show --id $APP_ID --query id -o tsv
$SUB = az account show --query id -o tsv

az role assignment create --assignee-object-id $SP_ID --assignee-principal-type ServicePrincipal `
  --role "Contributor" --scope "/subscriptions/$SUB/resourceGroups/secops-tfstate-rg"

az role assignment create --assignee-object-id $SP_ID --assignee-principal-type ServicePrincipal `
  --role "Contributor" --scope "/subscriptions/$SUB/resourceGroups/secops-dev-cin-rg"
```

> **Say this in the viva.** We granted Contributor on two **resource groups**, not on the subscription. Our own `CAF-IAM-001` rule flags subscription-scoped Contributor as CRITICAL. We held our own infrastructure to the standard the tool enforces on everyone else. The cost of that decision is one extra step in Part 5 (a `terraform import`), and it is worth it.

## 3.5 Set a budget alert — do not skip this

A student subscription has **no hard spending cap**. A forgotten VM will quietly drain the whole grant. The budget alert is your safety net.

**Portal:** Home → **Cost Management + Billing** → select your subscription → **Budgets** → **+ Add**
- Scope: your subscription
- Name: `secops-monthly-budget`
- Reset period: **Monthly**
- Amount: **500** (in your billing currency)
- Next → Alert conditions: **50%**, **80%**, **100%** of budget
- Alert recipients: your email
- Create

**CLI:**

```powershell
az consumption budget create `
  --budget-name secops-monthly-budget `
  --amount 500 --category Cost --time-grain Monthly `
  --start-date (Get-Date -Format "yyyy-MM-01") `
  --end-date (Get-Date).AddMonths(12).ToString("yyyy-MM-01")
```

If the CLI refuses (common on student subscriptions), use the portal. Do not move on without a budget set.

---

# Part 4 — Connect GitHub to Azure

You now have four values. Collect them:

```powershell
echo "AZURE_CLIENT_ID       = $APP_ID"
az account show --query "{AZURE_TENANT_ID:tenantId, AZURE_SUBSCRIPTION_ID:id}" -o table
echo "TFSTATE_SA            = $SA"
```

## 4.1 Add the secrets

In your repo: **Settings** → **Secrets and variables** → **Actions** → **Secrets** tab → **New repository secret**. Add three:

| Name | Value |
|---|---|
| `AZURE_CLIENT_ID` | your Application (client) ID |
| `AZURE_TENANT_ID` | your tenant ID |
| `AZURE_SUBSCRIPTION_ID` | your subscription ID |

> These are identifiers, not passwords. There is no credential here to leak — that is the whole point of OIDC.

## 4.2 Add the variables

Same page, **Variables** tab → **New repository variable**. Add two:

| Name | Value |
|---|---|
| `TFSTATE_RG` | `secops-tfstate-rg` |
| `TFSTATE_SA` | your generated storage account name |

## 4.3 Create the protected environment

**Settings** → **Environments** → **New environment** → name it exactly `production` → Configure.

Tick **Required reviewers** and add yourself. Save.

This gives you a **second, human control** on top of the automated gate: even when the gate passes, `terraform apply` waits for a click. Worth demonstrating.

---

# Part 5 — Deploy once from your laptop

Do this before touching the pipeline, so that when the pipeline runs you already know the module is good.

## 5.1 Configure the module

```powershell
cd infra\demo
copy terraform.tfvars.example terraform.tfvars
notepad terraform.tfvars
```

Set `owner` to your email. Leave everything else — the defaults are the cheapest compliant configuration.

## 5.2 Initialise with the remote backend

```powershell
terraform init `
  -backend-config="resource_group_name=secops-tfstate-rg" `
  -backend-config="storage_account_name=$SA" `
  -backend-config="container_name=tfstate" `
  -backend-config="key=demo.tfstate"
```

Expect: `Terraform has been successfully initialized!`

## 5.3 Import the pre-created resource group

Remember Part 3.4.3 — the service principal has permission **on** the resource groups but not to create new ones. You already created `secops-dev-cin-rg` by hand, so tell Terraform it exists rather than letting it try to create it:

```powershell
$SUB = az account show --query id -o tsv
terraform import azurerm_resource_group.rg "/subscriptions/$SUB/resourceGroups/secops-dev-cin-rg"
```

Expect: `Import successful!`. This is a one-time step.

> Alternative if you would rather skip this: grant the service principal Contributor at **subscription** scope instead, and Terraform can create resource groups itself. It is simpler and it is what most tutorials do — but it is a broader grant than the workload needs, which is exactly what `CAF-IAM-001` exists to discourage. Your call; know the trade-off.

## 5.4 Plan, then gate, then apply — in that order

```powershell
terraform plan -out=tf.plan
terraform show -json tf.plan > plan.json
```

Now run the gate, exactly as CI will run it:

```powershell
cd ..\..
python -m agent.cli evaluate --plan infra/demo/plan.json --policy policies/policy.yaml
echo $LASTEXITCODE
```

**Only if that prints PASS and exit code 0:**

```powershell
cd infra\demo
terraform apply tf.plan
```

**That ordering — plan, gate, apply — is the entire thesis of the project.** Do it in that order in your demo, and say out loud that apply is unreachable when the gate returns 2.

## 5.5 Confirm what you deployed

```powershell
terraform output
az resource list --resource-group secops-dev-cin-rg --output table
```

You should see exactly three things: a storage account, a Log Analytics workspace, and a diagnostic setting. Nothing else. Current cost: about ₹2/month.

---

# Part 6 — Run the pipeline end to end

## 6.1 Make a branch and open a pull request

```powershell
cd "d:\Code\SecOps Agent for CAFWAF compliant Cloud Deployments in CICD"

git checkout -b demo/gate-in-action
```

Make a small change so there is something to review — for example open `infra/demo/terraform.tfvars` and change the `owner` value. Then:

```powershell
git add .
git commit -m "Demo: trigger the compliance gate"
git push -u origin demo/gate-in-action
```

Go to your repo in the browser; GitHub offers a **Compare & pull request** button. Click it, then **Create pull request**.

## 6.2 What you should see

Open the **Actions** tab and watch. In order:

1. **Agent unit tests** runs first. If the gate's own tests fail, its verdicts mean nothing, so nothing downstream is allowed to run.
2. **Two plan jobs run in parallel:**
   - `compliant-workload` — plans `infra/demo`, must **PASS**
   - `seeded-misconfigurations` — plans `examples/terraform/noncompliant`, must **BLOCK**
3. A **compliance report comment** appears on the pull request, naming each violated pillar with a copy-pasteable HCL fix.
4. Findings appear under the **Security** tab → Code scanning alerts.

> The second job is the interesting one. It is *expected* to be blocked, and the workflow **fails the build if it is not** — that is the regression test for the gate itself, running on every change.

## 6.3 Prove the gate actually blocks

This is the demo that lands. On your branch, break something deliberately:

```powershell
notepad infra\demo\terraform.tfvars
```

Change `public_network_access = false` to `true`, then:

```powershell
git add . ; git commit -m "Demo: open the storage account to the internet" ; git push
```

The pipeline re-runs and the `compliant-workload` job now **fails**, with a PR comment saying:

> **CAF-LZ-002** · `CAF:LandingZone` · HIGH — Public network access is enabled, so the service is reachable from outside the landing-zone virtual network.

Nothing was deployed. Revert it and watch the pipeline go green:

```powershell
git revert HEAD --no-edit ; git push
```

## 6.4 Merge and deploy

Merge the pull request. On `main`, the **apply** job starts and then **waits for your approval** because of the protected environment. Approve it in the Actions tab, and Terraform applies.

---

# Part 7 — Tear down

Do this at the end of every session. The footprint takes two minutes to recreate, so there is no reason to leave it running.

```powershell
cd infra\demo
terraform destroy
```

Then confirm nothing expensive is left anywhere in the subscription:

```powershell
az resource list --query "[?contains(type,'virtualMachines') || contains(type,'managedClusters') || contains(type,'servers') || contains(type,'serverFarms')].{name:name,type:type,rg:resourceGroup}" -o table
```

That should print nothing. If it prints something, you did not create it as part of this project — investigate it.

Keep `secops-tfstate-rg` between sessions; it costs about ₹2/month and rebuilding it means redoing Part 3.3 and Part 5.2. Delete it only when the project is finished:

```powershell
az group delete --name secops-dev-cin-rg --yes --no-wait
# only at the very end of the project:
# az group delete --name secops-tfstate-rg --yes --no-wait
```

Check your actual spend any time: **Portal → Cost Management + Billing → Cost analysis**, grouped by resource.

---

# Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `AADSTS70021: No matching federated identity record found` | The federated credential subject does not match the workflow context. Check the repo name is exactly right, and that all three credentials from 3.4.2 exist. |
| `Error: building account: could not acquire access token` | `az login` expired, or `permissions: id-token: write` is missing from the workflow. It is already there in ours. |
| `StorageAccountAlreadyTaken` | Storage names are globally unique across all of Azure. Generate a new random suffix and retry. |
| `AuthorizationFailed` on apply | RBAC takes a few minutes to propagate after Part 3.4.3. Wait, then retry. |
| `A resource with the ID ... already exists` | Terraform is trying to create the resource group you made by hand. Run the `terraform import` from 5.3. |
| `Error acquiring the state lock` | A previous run died mid-apply. Read the message for the lock ID, then `terraform force-unlock <ID>`. |
| Gate blocks your own module | Read the report — it names the pillar and gives the fix. That is the gate working, not failing. |
| `python` opens the Microsoft Store | Settings → Apps → Advanced app settings → App execution aliases → turn off both `python.exe` entries. |
| Actions fail on a fork's pull request | Forked PRs do not receive secrets, by GitHub's design. Push branches to your own repo instead. |

---

# Quick reference

```powershell
# Run the agent (no cloud needed)
python -m agent.cli evaluate --plan examples/plans/azure_noncompliant.plan.json

# Full local demo
bash scripts/demo.sh

# The real cycle: plan -> gate -> apply
cd infra\demo
terraform plan -out=tf.plan
terraform show -json tf.plan > plan.json
cd ..\..
python -m agent.cli evaluate --plan infra/demo/plan.json    # exit 0 required
cd infra\demo ; terraform apply tf.plan

# Session hygiene
bash scripts/azure-cost-check.sh      # before you start
terraform destroy                     # when you finish
```
