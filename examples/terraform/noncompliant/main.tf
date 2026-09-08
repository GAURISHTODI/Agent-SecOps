###############################################################################
# SEEDED MISCONFIGURATION MODULE -- PLAN ONLY, NEVER APPLY
#
# This is the test set the project's success metric is measured against:
# intentionally misconfigured Terraform whose every violation is labelled
# below with the rule that must catch it.
#
# It costs nothing because it is only ever run through `terraform plan`.
# The gate blocks it, so `terraform apply` is never reached -- which is the
# whole point of the project: the misconfiguration is stopped before any
# resource, and any spend, exists.
#
# DO NOT add a backend or run apply against this directory.
###############################################################################

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

provider "azurerm" {
  features {}
  skip_provider_registration = true
}

# VIOLATION: CAF-LZ-001 (unapproved region), CAF-GOV-001 (no tags),
#            CAF-GOV-002 (naming standard)
resource "azurerm_resource_group" "rg" {
  name     = "demo-rg"
  location = "brazilsouth"
}

# VIOLATIONS:
#   WAF-SEC-001  https_traffic_only_enabled = false
#   WAF-SEC-002  min_tls_version = TLS1_0
#   WAF-SEC-003  allow_nested_items_to_be_public = true
#   WAF-REL-001  LRS replication on production data
#   CAF-LZ-002   public_network_access_enabled = true
#   CAF-GOV-001  missing owner/environment/costcenter tags
#   WAF-SUS-001  archive-class data left in the Hot tier
#   reasoner     network_rules default_action = Allow
#   reasoner     shared access keys enabled
#   reasoner     versioning disabled
resource "azurerm_storage_account" "data" {
  name                = "demodatastore001"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location

  account_tier             = "Standard"
  account_replication_type = "LRS"
  access_tier              = "Hot"

  https_traffic_only_enabled      = false
  min_tls_version                 = "TLS1_0"
  allow_nested_items_to_be_public = true
  shared_access_key_enabled       = true
  public_network_access_enabled   = true

  network_rules {
    default_action = "Allow"
  }

  tags = {
    dataclass = "archive"
  }
}

# VIOLATIONS:
#   WAF-SEC-006  administrator_login_password hardcoded
#   WAF-SEC-002  minimum_tls_version = 1.0
#   WAF-REL-002  backup_retention_days = 1
#   CAF-LZ-002   public_network_access_enabled = true
#   CAF-GOV-001  missing owner/costcenter
resource "azurerm_mssql_server" "db" {
  name                = "demo-sql-server"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  version             = "12.0"

  administrator_login          = "sqladmin"
  administrator_login_password = "P@ssw0rd123!" # never do this

  minimum_tls_version           = "1.0"
  public_network_access_enabled = true

  tags = {
    environment = "prod"
  }
}

# VIOLATION: reasoner -- firewall rule spanning the entire IPv4 space
resource "azurerm_mssql_firewall_rule" "allow_all" {
  name             = "allow-all"
  server_id        = azurerm_mssql_server.db.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "255.255.255.255"
}

# VIOLATION: WAF-SEC-004 -- SSH open to the internet
resource "azurerm_network_security_rule" "ssh" {
  name                        = "allow-ssh-any"
  resource_group_name         = azurerm_resource_group.rg.name
  network_security_group_name = "demo-nsg"

  priority                   = 100
  direction                  = "Inbound"
  access                     = "Allow"
  protocol                   = "Tcp"
  source_port_range          = "*"
  destination_port_range     = "22"
  source_address_prefix      = "*"
  destination_address_prefix = "*"
}

# VIOLATIONS:
#   WAF-SEC-006  admin_password hardcoded
#   WAF-COST-001 premium D8s SKU on a dev workload
#   CAF-COST-001 no costcenter tag on a billable resource
#   reasoner     password authentication enabled
#   reasoner     no availability zone or set
resource "azurerm_linux_virtual_machine" "app" {
  name                = "demo-vm"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  size                = "Standard_D8s_v3"

  admin_username                  = "azureuser"
  admin_password                  = "SuperSecret#2026"
  disable_password_authentication = false

  network_interface_ids = []

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts"
    version   = "latest"
  }

  tags = {
    environment = "dev"
    owner       = "team-a"
  }
}

# VIOLATION: CAF-IAM-001 -- Owner at subscription scope
resource "azurerm_role_assignment" "app_owner" {
  scope                = "/subscriptions/00000000-0000-0000-0000-000000000000"
  role_definition_name = "Owner"
  principal_id         = "11111111-1111-1111-1111-111111111111"
}

# VIOLATIONS:
#   WAF-REL-003  purge protection disabled
#   CAF-LZ-002   public network access enabled
#   reasoner     access policies instead of RBAC
resource "azurerm_key_vault" "kv" {
  name                = "demo-kv"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  tenant_id           = "22222222-2222-2222-2222-222222222222"
  sku_name            = "standard"

  purge_protection_enabled      = false
  soft_delete_retention_days    = 7
  enable_rbac_authorization     = false
  public_network_access_enabled = true

  tags = {
    environment = "prod"
    owner       = "team-a"
    costcenter  = "CC-1042"
  }
}

# VIOLATIONS: CAF-LZ-003 (no exposure justification), WAF-COST-002 (static IP in dev)
resource "azurerm_public_ip" "edge" {
  name                = "demo-pip"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = {
    environment = "dev"
  }
}
