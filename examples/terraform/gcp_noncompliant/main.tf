###############################################################################
# SEEDED MISCONFIGURATION MODULE (GCP) -- PLAN ONLY, NEVER APPLY
#
# Mirrors examples/plans/gcp_noncompliant.plan.json as real Terraform. No
# credentials are configured; none of these resources reads from GCP during
# `terraform plan -refresh=false`, so it runs offline and costs nothing.
###############################################################################

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = "demo-project"
  region  = "southamerica-east1"

  # Dummy token: skips Application Default Credentials so plan runs offline.
  access_token = "offline"
}

# VIOLATIONS: CAF-LZ-001 region, WAF-REL-001 no versioning, CAF-GOV-001 labels
resource "google_storage_bucket" "data" {
  name          = "demo-data-bucket"
  location      = "SOUTHAMERICA-EAST1"
  storage_class = "STANDARD"
  labels        = { environment = "prod" }

  versioning {
    enabled = false
  }
}

# VIOLATION: WAF-SEC-004 SSH and RDP open to the internet
resource "google_compute_firewall" "allow_ssh" {
  name          = "allow-ssh"
  network       = "default"
  direction     = "INGRESS"
  source_ranges = ["0.0.0.0/0"]

  allow {
    protocol = "tcp"
    ports    = ["22", "3389"]
  }
}

# VIOLATIONS: WAF-SEC-006 plaintext password, WAF-REL-002 no backups,
#             WAF-OPS-002 deletion protection off
resource "google_sql_database_instance" "main" {
  name                = "demo-sql"
  region              = "southamerica-east1"
  database_version    = "POSTGRES_15"
  deletion_protection = false
  root_password       = "changeme123"

  settings {
    tier = "db-f1-micro"
    backup_configuration {
      enabled = false
    }
    user_labels = { environment = "dev" }
  }
}

# VIOLATION: CAF-IAM-001 primitive owner role
resource "google_project_iam_member" "owner" {
  project = "demo-project"
  role    = "roles/owner"
  member  = "serviceAccount:app@demo-project.iam.gserviceaccount.com"
}
