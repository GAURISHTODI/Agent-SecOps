###############################################################################
# Variables. Defaults are chosen for the cheapest safe configuration, so an
# accidental `terraform apply` with no tfvars costs almost nothing.
###############################################################################

variable "workload" {
  description = "Workload name used as the naming prefix (CAF-GOV-002)."
  type        = string
  default     = "secops"

  validation {
    condition     = can(regex("^[a-z0-9]+$", var.workload))
    error_message = "Workload must be lowercase alphanumeric to satisfy the naming standard."
  }
}

variable "environment" {
  description = "Environment tier. Drives both the naming standard and the cost rules."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "test", "stage", "prod"], var.environment)
    error_message = "Environment must be one of: dev, test, stage, prod."
  }
}

variable "location" {
  description = "Azure region. Must be in the approved landing-zone list (CAF-LZ-001)."
  type        = string
  default     = "centralindia"

  validation {
    # Enforcing the landing-zone region list twice -- here at author time and
    # again in the gate at pipeline time -- is deliberate defence in depth.
    condition     = contains(["centralindia", "southindia", "eastus"], var.location)
    error_message = "Location must be an approved landing-zone region."
  }
}

variable "region_short" {
  description = "Short region code for resource names."
  type        = string
  default     = "cin"
}

variable "owner" {
  description = "Owning team email (CAF-GOV-001)."
  type        = string
  default     = "platform-team@example.com"
}

variable "cost_center" {
  description = "Cost centre for budget attribution (CAF-COST-001)."
  type        = string
  default     = "CC-1042"
}

variable "replication_type" {
  description = <<-EOT
    Storage replication. LRS is the cheapest and is fine below production;
    the gate (WAF-REL-001) only demands ZRS/GRS for prod-tagged accounts,
    so the default here keeps demo spend at its floor.
  EOT
  type        = string
  default     = "LRS"
}

variable "public_network_access" {
  description = <<-EOT
    Whether the storage account is reachable from the public internet.

    Defaults to false, which is both free and compliant: disabling public
    network access costs nothing, and it is what lets this module pass its
    own gate cleanly. A real landing zone would then add a private endpoint
    for access -- we skip that because private endpoints cost roughly
    Rs 600/month each, far more than the rest of this module combined, and
    nothing in the demo needs to read the blob.

    Flip this to true if you want to browse the container in the portal: the
    gate will immediately flag it as CAF-LZ-002 (HIGH) and block the deploy,
    which is a useful thing to demonstrate live.
  EOT
  type        = bool
  default     = false
}

variable "allowed_ip_rules" {
  description = "Source IPs permitted through the storage firewall."
  type        = list(string)
  default     = []
}

variable "log_daily_quota_gb" {
  description = <<-EOT
    Hard daily ingestion cap on Log Analytics. 0.1 GB keeps the workspace
    inside the free tier permanently; ingestion simply stops rather than
    billing once the cap is hit.
  EOT
  type        = number
  default     = 0.1
}

variable "use_oidc" {
  description = "Authenticate via GitHub OIDC federation (true in CI, false locally)."
  type        = bool
  default     = false
}
