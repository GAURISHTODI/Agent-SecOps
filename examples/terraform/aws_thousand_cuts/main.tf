###############################################################################
# SEEDED DEPENDENCY-GRAPH MODULE (AWS) -- "A THOUSAND SMALL CUTS"
# PLAN ONLY, NEVER APPLY
#
# Six small web servers each get their own public IP. Nobody opens a port to
# the internet and the database is private. Judged one at a time, nothing
# here is alarming:
#
#   each public IP     a MEDIUM governance note (no exposure justification)
#   each web server    healthy: no findings of its own
#   the database       private, not internet-reachable, so the graph scores
#                      it 0.00 on its own
#
# The catch is one shortcut taken to save time: the database reuses the web
# tier's security group instead of having its own. That puts every public IP
# three hops from the database:
#
#   public IP[i] -> web server[i] -> shared "app" security group -> database
#
# One public IP 3 hops away adds only 0.55 x 0.75^3 = 0.23 exposure: a risk
# of 0.19, too small to report. Six of them add up (noisy-OR) to 0.80, and
# the risk becomes 0.80 x 0.83 x 1.00 = 0.66: HIGH. No single door matters;
# the number of doors does.
#
# Asserted in tests/test_graph_complex.py, including that three doors give a
# medium risk and one door gives nothing.
#
# Dummy credentials and skipped API checks: plans offline, costs nothing.
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
    owner       = "storefront-team@example.com"
    environment = "prod"
    costcenter  = "CC-3100"
  }
  vpc_id = "vpc-0offline0000000002"
  subnet = "subnet-0offline000000010"
}

# Internal only: accepts traffic from inside the VPC, never from the internet.
resource "aws_security_group" "app" {
  name   = "shop-prod-aps1-app-sg"
  vpc_id = local.vpc_id

  ingress {
    from_port   = 0
    to_port     = 65535
    protocol    = "tcp"
    cidr_blocks = ["10.20.0.0/16"]
  }
  tags = local.tags
}

# Healthy web servers: nothing for a single-resource rule to object to.
resource "aws_instance" "web" {
  count                  = 6
  ami                    = "ami-0offline000000002"
  instance_type          = "t3.micro"
  subnet_id              = local.subnet
  vpc_security_group_ids = [aws_security_group.app.id]
  tags                   = local.tags
}

# Each one: CAF-LZ-003 (MEDIUM) -- a public IP with no exposure justification.
resource "aws_eip" "web" {
  count    = 6
  domain   = "vpc"
  instance = aws_instance.web[count.index].id
  tags     = local.tags
}

# Private (publicly_accessible = false) and backed up. Its own weakness is a
# password typed into the code (WAF-SEC-006), which the team accepted
# because "nothing can reach it". The shared security group is what makes
# that untrue.
resource "aws_db_instance" "billing" {
  identifier              = "shop-prod-aps1-billing"
  engine                  = "postgres"
  instance_class          = "db.t3.micro"
  allocated_storage       = 20
  username                = "billing"
  password                = "Billing#2026!"
  backup_retention_period = 7
  skip_final_snapshot     = false
  publicly_accessible     = false
  storage_encrypted       = true
  vpc_security_group_ids  = [aws_security_group.app.id]
  tags                    = local.tags
}
