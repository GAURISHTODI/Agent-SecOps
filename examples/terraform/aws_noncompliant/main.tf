###############################################################################
# SEEDED MISCONFIGURATION MODULE (AWS) -- PLAN ONLY, NEVER APPLY
#
# Mirrors examples/plans/aws_noncompliant.plan.json, but as real Terraform so
# CI produces a genuine `terraform show -json` from it. The provider is
# configured with dummy credentials and every AWS API check switched off, so
# `terraform plan` needs no AWS account and costs nothing.
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
  region     = "sa-east-1"
  access_key = "offline"
  secret_key = "offline"

  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
  skip_region_validation      = true
}

# VIOLATIONS: WAF-SEC-003 public-read ACL, CAF-LZ-001 region, CAF-GOV-001 tags
resource "aws_s3_bucket" "data" {
  bucket = "demo-data-bucket"
  tags   = { environment = "prod" }
}

resource "aws_s3_bucket_acl" "data" {
  bucket = aws_s3_bucket.data.id
  acl    = "public-read"
}

# VIOLATION: WAF-SEC-004 SSH and Postgres open to the internet
resource "aws_security_group" "web" {
  name        = "web-sg"
  description = "web tier"

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# VIOLATIONS: WAF-SEC-006 plaintext password, WAF-REL-002 no backups,
#             WAF-OPS-002 skip final snapshot, WAF-COST-001 premium dev SKU
resource "aws_db_instance" "main" {
  identifier              = "demo-db"
  instance_class          = "db.m5.2xlarge"
  engine                  = "postgres"
  allocated_storage       = 20
  username                = "dbadmin"
  password                = "Sup3rSecret!"
  backup_retention_period = 0
  skip_final_snapshot     = true
  publicly_accessible     = true
  tags                    = { environment = "dev", owner = "team-b" }
}

# VIOLATION: CAF-IAM-001 wildcard actions
resource "aws_iam_role" "app" {
  name = "app-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "admin" {
  name = "admin-policy"
  role = aws_iam_role.app.id
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "*", Resource = "*" }]
  })
}
