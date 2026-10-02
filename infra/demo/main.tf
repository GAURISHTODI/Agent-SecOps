###############################################################################
# Agent SecOps -- minimal compliant demo workload
#
# COST NOTE (read before running `apply`):
# This module is deliberately built from the cheapest Azure resources that
# still exercise every CAF/WAF pillar the gate checks:
#
#   azurerm_resource_group          free
#   azurerm_storage_account         ~Rs 2/month at demo volume (few MB, ZRS)
#   azurerm_log_analytics_workspace free tier (5 GB/month) + 0.1 GB daily cap
#   azurerm_monitor_diagnostic_setting  free
#
# There is no VM, no AKS cluster, no SQL Server and no App Service plan --
# those are the four resources that actually burn student credits. The gate
# is still demonstrated against them using plan-only fixtures in
# examples/plans/, which cost nothing because they are never applied.
#
# Expected steady-state spend: under Rs 50/month. Run scripts/azure-destroy
# after each demo to take it to zero.
###############################################################################

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }

  # State lives in the storage account created by scripts/azure-bootstrap.sh.
  # Values are supplied by -backend-config in CI so no secret is committed.
  backend "azurerm" {}
}

provider "azurerm" {
  features {}
  # Authentication comes from GitHub OIDC in CI (no client secret stored) and
  # from `az login` locally.
  use_oidc = var.use_oidc

  # The storage account below sets shared_access_key_enabled = false (WAF
  # Security: no shared keys). Without this flag the provider still tries to
  # read queue/table properties using an account key when refreshing state,
  # which now returns 403 Key based authentication is not permitted. Forcing
  # Azure AD auth for the provider's own management calls keeps that read
  # working without reopening key-based access.
  storage_use_azuread = true
}

locals {
  # One tag block, applied everywhere. This is what satisfies CAF-GOV-001,
  # and it is why the compliant plan passes the gate with zero findings.
  common_tags = {
    owner       = var.owner
    environment = var.environment
    costcenter  = var.cost_center
    monitoring  = "law"
    project     = "agent-secops"
  }

  # <workload>-<env>-<region>-<type>, per CAF-GOV-002.
  prefix = "${var.workload}-${var.environment}-${var.region_short}"
}

resource "azurerm_resource_group" "rg" {
  name     = "${local.prefix}-rg"
  location = var.location
  tags     = local.common_tags
}

# --- Observability -----------------------------------------------------
# Free-tier workspace with a hard daily cap, so a runaway log source can
# never eat the credit pool. This is WAF Operational Excellence and WAF
# Cost Optimization satisfied by the same resource.
resource "azurerm_log_analytics_workspace" "law" {
  name                = "${local.prefix}-law"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name

  sku               = "PerGB2018"
  retention_in_days = 30
  daily_quota_gb    = var.log_daily_quota_gb # 0.1 GB -- a hard cost ceiling

  tags = local.common_tags
}

# --- Data tier ---------------------------------------------------------
# Storage account names cannot contain hyphens, which is exactly why
# CAF-GOV-002 exempts object_storage in policies/policy.yaml.
resource "azurerm_storage_account" "data" {
  name                = replace("${local.prefix}data", "-", "")
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location

  account_tier             = "Standard"
  account_replication_type = var.replication_type # ZRS in prod, LRS in dev
  access_tier              = "Hot"

  # --- WAF Security ---
  https_traffic_only_enabled      = true  # WAF-SEC-001
  min_tls_version                 = "TLS1_2" # WAF-SEC-002
  allow_nested_items_to_be_public = false # WAF-SEC-003
  shared_access_key_enabled       = false # reasoner: prefer Entra ID auth
  public_network_access_enabled   = var.public_network_access # CAF-LZ-002

  # --- WAF Reliability ---
  blob_properties {
    versioning_enabled = true

    delete_retention_policy {
      days = 7
    }
  }

  # --- CAF Landing Zone: default-deny network posture ---
  network_rules {
    default_action = var.public_network_access ? "Allow" : "Deny"
    bypass         = ["AzureServices"]
    ip_rules       = var.allowed_ip_rules
  }

  tags = local.common_tags
}

# Ships storage logs to the workspace, which is what clears WAF-OPS-001.
resource "azurerm_monitor_diagnostic_setting" "storage" {
  name                       = "${local.prefix}-storage-diag"
  target_resource_id         = azurerm_storage_account.data.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.law.id

  enabled_metric {
    category = "Transaction"
  }
}
