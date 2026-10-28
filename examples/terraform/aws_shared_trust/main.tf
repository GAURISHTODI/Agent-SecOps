###############################################################################
# SEEDED DEPENDENCY-GRAPH MODULE (AWS) -- "THREE TEAMS, ONE SHARED KEY"
# PLAN ONLY, NEVER APPLY
#
# Three teams each own a module, and each module passes its own review:
#
#   module.storefront   3 web servers with public IPs, no weakness anywhere
#   module.analytics    a reporting database that is publicly accessible but
#                       well secured (AWS-managed password, encryption, backups)
#   module.ledger       the payments database: private, so "safe", even though
#                       its password is typed into the code and it keeps only
#                       one day of backups
#
# The platform team, in the root module, hands all three the same two shared
# resources: one internal security group and one KMS key. Those two shared
# objects are the only thing connecting the teams, and they connect the
# ledger to every public thing in the estate:
#
#   public IP[i] -> storefront server[i] -> shared security group -> ledger
#                                                              (3 hops, x3)
#   analytics database -> shared KMS key -> ledger              (2 hops)
#
# Exposure reaching the ledger: three small 0.23 paths plus one 0.39 path,
# combined = 0.73. Ledger weakness 0.92, value 1.00: risk 0.67, HIGH. Take
# any one team's module on its own and the graph finds nothing; any two
# teams give at most a medium risk.
#
# Because the shared resources are passed into modules as variables, the
# gate has to follow var.* references across the module boundary to see this.
#
# Asserted in tests/test_graph_complex.py. Dummy credentials: plans offline.
###############################################################################

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region     = "ap-south-1"
  access_key = "offline"
  secret_key = "offline"

  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
  skip_region_validation      = true
}

locals {
  tags = {
    owner       = "platform-team@example.com"
    environment = "prod"
    costcenter  = "CC-4200"
  }
  vpc_id = "vpc-0offline0000000003"
  subnet = "subnet-0offline000000020"
}

# --- platform team: the two shared resources -------------------------------

# Internal only; nothing here is open to the internet.
resource "aws_security_group" "internal" {
  name   = "corp-prod-aps1-internal-sg"
  vpc_id = local.vpc_id

  ingress {
    from_port   = 0
    to_port     = 65535
    protocol    = "tcp"
    cidr_blocks = ["10.30.0.0/16"]
  }
  tags = local.tags
}

# One key for every team's data, rotated: a sensible-looking saving.
resource "aws_kms_key" "shared" {
  description             = "corp shared data key"
  deletion_window_in_days = 7
  enable_key_rotation     = true
  tags                    = local.tags
}

# --- the three teams --------------------------------------------------------

module "storefront" {
  source = "./modules/storefront"
  sg_id  = aws_security_group.internal.id
  subnet = local.subnet
  tags   = local.tags
}

module "analytics" {
  source      = "./modules/analytics"
  kms_key_arn = aws_kms_key.shared.arn
  tags        = local.tags
}

module "ledger" {
  source      = "./modules/ledger"
  sg_id       = aws_security_group.internal.id
  kms_key_arn = aws_kms_key.shared.arn
  tags        = local.tags
}
