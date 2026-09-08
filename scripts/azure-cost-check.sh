#!/usr/bin/env bash
###############################################################################
# Credit watchdog. Run this before and after every demo session.
#
# On a student subscription there is no hard spending cap -- a forgotten VM
# quietly drains the pool. This script answers three questions:
#   1. What am I spending this month?
#   2. What expensive resources exist right now?
#   3. Is anything running that should not be?
###############################################################################
set -euo pipefail

SUBSCRIPTION_ID=$(az account show --query id -o tsv)
echo "Subscription: $(az account show --query name -o tsv)"
echo

echo "=== Month-to-date spend ==="
az consumption usage list \
  --start-date "$(date +%Y-%m-01)" \
  --end-date "$(date +%Y-%m-%d)" \
  --query "[].{cost:pretaxCost,currency:currency,resource:instanceName}" \
  -o tsv 2>/dev/null \
  | awk '{sum += $1; cur=$2} END {printf "Total: %.2f %s\n", sum, cur}' \
  || echo "(consumption API not available on this subscription type --
 check Cost Management > Cost analysis in the portal)"
echo

echo "=== Resources that actually cost money ==="
# These are the resource types capable of draining credits quickly. Anything
# listed here on a student subscription deserves a second look.
az resource list \
  --query "[?contains(type,'virtualMachines') ||
            contains(type,'managedClusters') ||
            contains(type,'servers') ||
            contains(type,'serverFarms') ||
            contains(type,'CognitiveServices') ||
            contains(type,'privateEndpoints') ||
            contains(type,'applicationGateways') ||
            contains(type,'azureFirewalls')]
           .{name:name,type:type,rg:resourceGroup,location:location}" \
  -o table || true
echo

echo "=== Everything in the project resource groups ==="
for RG in $(az group list --query "[?tags.project=='agent-secops'].name" -o tsv); do
  echo "--- $RG ---"
  az resource list --resource-group "$RG" \
    --query "[].{name:name,type:type}" -o table
done
echo

echo "=== Running VMs (the classic credit drain) ==="
az vm list -d --query "[?powerState=='VM running'].{name:name,size:hardwareProfile.vmSize,rg:resourceGroup}" \
  -o table 2>/dev/null || echo "(no VMs)"

echo
echo "If anything above is unexpected, tear it down: bash scripts/azure-destroy.sh"
