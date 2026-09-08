output "resource_group_name" {
  description = "Resource group holding the demo workload."
  value       = azurerm_resource_group.rg.name
}

output "storage_account_name" {
  description = "Storage account the gate reasons about."
  value       = azurerm_storage_account.data.name
}

output "log_analytics_workspace_id" {
  description = "Workspace collecting diagnostics (satisfies WAF-OPS-001)."
  value       = azurerm_log_analytics_workspace.law.id
}

output "monthly_cost_note" {
  description = "Reminder of the intended spend envelope for this module."
  value       = "Demo footprint only: storage (few MB) + free-tier Log Analytics. Run scripts/azure-destroy.sh to return to zero."
}
