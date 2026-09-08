#!/usr/bin/env bash
###############################################################################
# Tear the demo footprint back down to zero spend.
#
# Run this at the end of every working session. The whole point of keeping
# the footprint tiny is that recreating it takes two minutes, so there is no
# reason to leave anything running between demos.
###############################################################################
set -euo pipefail

PREFIX="${PREFIX:-secops}"
KEEP_STATE="${KEEP_STATE:-true}"   # keep the tfstate account by default

echo "This will delete the Agent SecOps demo resources."
echo "Terraform state storage will be $([ "$KEEP_STATE" = "true" ] && echo KEPT || echo DELETED)."
read -rp "Type 'destroy' to continue: " CONFIRM
[[ "$CONFIRM" == "destroy" ]] || { echo "Aborted."; exit 1; }

# Preferred path: let Terraform remove exactly what it created, so state
# stays consistent.
if [[ -d infra/demo/.terraform ]]; then
  echo "==> terraform destroy"
  (cd infra/demo && terraform destroy -auto-approve) || \
    echo "    (terraform destroy failed; falling back to group deletion)"
fi

echo "==> Deleting workload resource groups tagged project=agent-secops"
for RG in $(az group list --query "[?tags.project=='agent-secops'].name" -o tsv); do
  if [[ "$KEEP_STATE" == "true" && "$RG" == *tfstate* ]]; then
    echo "    keeping $RG (Terraform state)"
    continue
  fi
  echo "    deleting $RG"
  az group delete --name "$RG" --yes --no-wait
done

echo
echo "Deletion running in the background. Verify with:"
echo "  bash scripts/azure-cost-check.sh"
