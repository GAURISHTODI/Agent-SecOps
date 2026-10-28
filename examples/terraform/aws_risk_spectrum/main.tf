###############################################################################
# SEEDED DEPENDENCY-GRAPH MODULE (AWS) -- "THE RISK SPECTRUM"
# PLAN ONLY, NEVER APPLY
#
# One internet-facing security group sits at the centre. Databases with the
# same kind of weakness are placed one, two, three and four hops away from
# it, so distance alone decides how risky each one is. Every colour in the
# dashboard's graph legend appears in this one plan:
#
#   exposed     the edge group, and a public-but-healthy analytics database
#   high        payments  -- in the edge group itself          (1 hop)
#   medium      orders    -- in a group the edge group can reach (2 hops)
#   low         reports   -- same 2 hops, but a smaller weakness
#   scored, not reported
#               archive   -- 3 hops: risk is visible but under the threshold
#   out of reach
#               vault     -- 4 hops: exposure never arrives
#   healthy     web servers in the edge group: reachable, nothing to exploit
#   isolated    an audit bucket linked to nothing exposed
#
#   internet ── edge SG ─┬─ web[0..2]           (healthy)
#     (all ports)        ├─ payments DB         HIGH
#                        └─ mid SG ─┬─ orders DB    MEDIUM
#                                   ├─ reports DB   LOW
#                                   └─ low SG ─┬─ archive DB  (scored only)
#                                              └─ vault SG ── vault DB (none)
#
#   analytics DB (publicly accessible, healthy)       audit bucket (isolated)
#
# Exact figures are asserted in tests/test_graph_complex.py.
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
    owner       = "platform-team@example.com"
    environment = "prod"
    costcenter  = "CC-5300"
  }
  vpc_id = "vpc-0offline0000000004"
  subnet = "subnet-0offline000000030"
}

# --- the centre: WAF-SEC-004, every port open to the internet -------------
resource "aws_security_group" "edge" {
  name   = "spec-prod-aps1-edge-sg"
  vpc_id = local.vpc_id

  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = local.tags
}

# Each ring only accepts traffic from the ring outside it.
resource "aws_security_group" "mid" {
  name   = "spec-prod-aps1-mid-sg"
  vpc_id = local.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.edge.id]
  }
  tags = local.tags
}

resource "aws_security_group" "low" {
  name   = "spec-prod-aps1-low-sg"
  vpc_id = local.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.mid.id]
  }
  tags = local.tags
}

resource "aws_security_group" "vault" {
  name   = "spec-prod-aps1-vault-sg"
  vpc_id = local.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.low.id]
  }
  tags = local.tags
}

# --- healthy web servers in the edge group --------------------------------
resource "aws_instance" "web" {
  count                  = 3
  ami                    = "ami-0offline000000004"
  instance_type          = "t3.micro"
  subnet_id              = local.subnet
  vpc_security_group_ids = [aws_security_group.edge.id]
  tags                   = local.tags
}

# --- databases, from closest to furthest ----------------------------------
# Weakness: plaintext password (WAF-SEC-006), no backups (WAF-REL-002),
# no customer-managed key (WAF-SEC-005).

# 1 hop -> HIGH
resource "aws_db_instance" "payments" {
  identifier              = "spec-prod-aps1-payments"
  engine                  = "postgres"
  instance_class          = "db.t3.micro"
  allocated_storage       = 20
  username                = "payments"
  password                = "Payments#2026!"
  backup_retention_period = 0
  skip_final_snapshot     = false
  vpc_security_group_ids  = [aws_security_group.edge.id]
  tags                    = local.tags
}

# 2 hops -> MEDIUM
resource "aws_db_instance" "orders" {
  identifier              = "spec-prod-aps1-orders"
  engine                  = "postgres"
  instance_class          = "db.t3.micro"
  allocated_storage       = 20
  username                = "orders"
  password                = "Orders#2026!"
  backup_retention_period = 0
  skip_final_snapshot     = false
  vpc_security_group_ids  = [aws_security_group.mid.id]
  tags                    = local.tags
}

# 2 hops, but backed up: a smaller weakness -> LOW
resource "aws_db_instance" "reports" {
  identifier              = "spec-prod-aps1-reports"
  engine                  = "postgres"
  instance_class          = "db.t3.micro"
  allocated_storage       = 20
  username                = "reports"
  password                = "Reports#2026!"
  backup_retention_period = 7
  skip_final_snapshot     = false
  vpc_security_group_ids  = [aws_security_group.mid.id]
  tags                    = local.tags
}

# 3 hops -> scored, but under the reporting threshold
resource "aws_db_instance" "archive" {
  identifier              = "spec-prod-aps1-archive"
  engine                  = "postgres"
  instance_class          = "db.t3.micro"
  allocated_storage       = 20
  username                = "archive"
  password                = "Archive#2026!"
  backup_retention_period = 7
  skip_final_snapshot     = false
  vpc_security_group_ids  = [aws_security_group.low.id]
  tags                    = local.tags
}

# 4 hops -> exposure never arrives
resource "aws_db_instance" "vault" {
  identifier              = "spec-prod-aps1-vault"
  engine                  = "postgres"
  instance_class          = "db.t3.micro"
  allocated_storage       = 20
  username                = "vault"
  password                = "Vault#2026!"
  backup_retention_period = 0
  skip_final_snapshot     = false
  vpc_security_group_ids  = [aws_security_group.vault.id]
  tags                    = local.tags
}

# --- exposed but healthy, and linked to nothing weak ----------------------
resource "aws_db_instance" "analytics" {
  identifier                  = "spec-prod-aps1-analytics"
  engine                      = "postgres"
  instance_class              = "db.t3.micro"
  allocated_storage           = 20
  username                    = "analytics"
  manage_master_user_password = true
  backup_retention_period     = 7
  skip_final_snapshot         = false
  publicly_accessible         = true
  storage_encrypted           = true
  kms_key_id                  = aws_kms_key.analytics.arn
  tags                        = local.tags
}

resource "aws_kms_key" "analytics" {
  description             = "analytics key"
  deletion_window_in_days = 7
  enable_key_rotation     = true
  tags                    = local.tags
}

# --- isolated and compliant -----------------------------------------------
resource "aws_s3_bucket" "audit" {
  bucket = "spec-prod-aps1-audit"
  tags   = local.tags
}

resource "aws_s3_bucket_versioning" "audit" {
  bucket = aws_s3_bucket.audit.id
  versioning_configuration {
    status = "Enabled"
  }
}
