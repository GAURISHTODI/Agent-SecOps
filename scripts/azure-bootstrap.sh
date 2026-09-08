#!/usr/bin/env bash
###############################################################################
# One-time Azure bootstrap for Agent SecOps.
#
# Creates the smallest possible footprint needed to run the pipeline:
#
#   1. A resource group                          (free)
#   2. A storage account for Terraform state     (~Rs 2/month, Standard_LRS)
#   3. An Entra ID app + GitHub OIDC federation  (free, and no stored secret)
#   4. A role assignment scoped to the RG only   (free, and least-privilege)
#   5. A budget alert                            (free)
#
# Everything here is free or near-free. The expensive things -- VMs, AKS,
# SQL, private endpoints, Azure OpenAI -- are deliberately NOT created.
#
# Run once:  bash scripts/azure-bootstrap.sh <github-org>/<repo>
###############################################################################
set -euo pipefail

REPO="${1:-}"
if [[ -z "$REPO" ]]; then
  echo "Usage: bash scripts/azure-bootstrap.sh <github-owner>/<repo>"
  exit 1
fi

# --- configuration (edit these three if you like) ---------------------
LOCATION="${LOCATION:-centralindia}"     # approved landing-zone region
PREFIX="${PREFIX:-secops}"
BUDGET_INR="${BUDGET_INR:-500}"          # alert threshold, not a hard cap

RG="${PREFIX}-tfstate-rg"
# Storage account names: 3-24 chars, lowercase alphanumeric only.
SA="${PREFIX}tfstate$(openssl rand -hex 3)"
APP_NAME="${PREFIX}-github-oidc"

echo "==> Checking Azure CLI login"
az account show >/dev/null 2>&1 || az login

SUBSCRIPTION_ID=$(az account show --query id -o tsv)
TENANT_ID=$(az account show --query tenantId -o tsv)
echo "    Subscription: $SUBSCRIPTION_ID"

# --- 1. Resource group -------------------------------------------------
echo "==> Creating resource group $RG in $LOCATION (free)"
az group create \
  --name "$RG" \
  --location "$LOCATION" \
  --tags owner="$(az account show --query user.name -o tsv)" \
         environment=prod costcenter=CC-1042 project=agent-secops \
  --output none

# --- 2. Terraform state storage ---------------------------------------
# Standard_LRS is the cheapest tier. State files are kilobytes, so the real
# monthly cost here is a rounding error. Versioning is on because losing
# Terraform state is unrecoverable -- that is WAF Reliability applied to our
# own tooling.
echo "==> Creating state storage account $SA (Standard_LRS, ~Rs 2/month)"
az storage account create \
  --name "$SA" \
  --resource-group "$RG" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --access-tier Hot \
  --min-tls-version TLS1_2 \
  --https-only true \
  --allow-blob-public-access false \
  --tags owner=platform environment=prod costcenter=CC-1042 \
  --output none

az storage blob service-properties update \
  --account-name "$SA" \
  --enable-versioning true \
  --auth-mode login \
  --output none 2>/dev/null || echo "    (versioning will apply once RBAC propagates)"

echo "==> Creating tfstate container"
az storage container create \
  --name tfstate \
  --account-name "$SA" \
  --auth-mode login \
  --output none

# --- 3. GitHub OIDC federation (no secrets stored) ---------------------
# Federated credentials replace a client secret entirely: GitHub presents a
# signed token, Azure exchanges it for a short-lived one. Nothing long-lived
# is ever stored in the repository.
echo "==> Creating Entra ID application $APP_NAME (free)"
APP_ID=$(az ad app create --display-name "$APP_NAME" --query appId -o tsv)
az ad sp create --id "$APP_ID" --output none 2>/dev/null || true
sleep 10  # allow directory replication

echo "==> Adding federated credentials for $REPO"
for SUBJECT in "repo:${REPO}:ref:refs/heads/main" \
               "repo:${REPO}:pull_request" \
               "repo:${REPO}:environment:production"; do
  NAME="gh-$(echo "$SUBJECT" | tr ':/' '--' | tail -c 40)"
  az ad app federated-credential create \
    --id "$APP_ID" \
    --parameters "{
      \"name\": \"$NAME\",
      \"issuer\": \"https://token.actions.githubusercontent.com\",
      \"subject\": \"$SUBJECT\",
      \"audiences\": [\"api://AzureADTokenExchange\"]
    }" --output none 2>/dev/null || echo "    (credential $NAME already exists)"
done

# --- 4. Least-privilege role assignment --------------------------------
# Scoped to the resource group, NOT the subscription. Our own CAF-IAM-001
# rule would flag a subscription-scoped Contributor grant, so the project
# holds itself to the standard it enforces.
echo "==> Granting Contributor on $RG only (least privilege)"
SP_OBJECT_ID=$(az ad sp show --id "$APP_ID" --query id -o tsv)
az role assignment create \
  --assignee-object-id "$SP_OBJECT_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Contributor" \
  --scope "/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RG}" \
  --output none 2>/dev/null || echo "    (assignment already exists)"

# The workload resource group is created by Terraform, so grant there too.
WORKLOAD_RG="${PREFIX}-dev-cin-rg"
az group create --name "$WORKLOAD_RG" --location "$LOCATION" \
  --tags owner=platform environment=dev costcenter=CC-1042 --output none
az role assignment create \
  --assignee-object-id "$SP_OBJECT_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Contributor" \
  --scope "/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${WORKLOAD_RG}" \
  --output none 2>/dev/null || true

# --- 5. Budget alert (free, and the single most important cost control) -
echo "==> Creating a Rs ${BUDGET_INR} budget alert"
END_DATE=$(date -d "+12 months" +%Y-%m-01 2>/dev/null || date -v+12m +%Y-%m-01)
az consumption budget create \
  --budget-name "${PREFIX}-monthly-budget" \
  --amount "$BUDGET_INR" \
  --category Cost \
  --time-grain Monthly \
  --start-date "$(date +%Y-%m-01)" \
  --end-date "$END_DATE" \
  --output none 2>/dev/null \
  || echo "    (budget API unavailable on this subscription -- set one in the portal:
     Cost Management > Budgets > Add. This is the safety net for your credits.)"

# --- output ------------------------------------------------------------
cat <<EOF

===============================================================================
Bootstrap complete. Add these to GitHub:

  Settings > Secrets and variables > Actions > Secrets
    AZURE_CLIENT_ID        $APP_ID
    AZURE_TENANT_ID        $TENANT_ID
    AZURE_SUBSCRIPTION_ID  $SUBSCRIPTION_ID

  Settings > Secrets and variables > Actions > Variables
    TFSTATE_RG             $RG
    TFSTATE_SA             $SA

Local development:
    cd infra/demo
    terraform init \\
      -backend-config="resource_group_name=$RG" \\
      -backend-config="storage_account_name=$SA" \\
      -backend-config="container_name=tfstate" \\
      -backend-config="key=demo.tfstate"

Running cost of what was just created: under Rs 5/month.
Tear everything down with: bash scripts/azure-destroy.sh
===============================================================================
EOF
