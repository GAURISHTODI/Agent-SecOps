###############################################################################
# SEEDED DEPENDENCY-GRAPH MODULE (AWS) -- PLAN ONLY, NEVER APPLY
#
# A three-tier application wired together the way real ones are: through
# security groups that reference each other. It exists to exercise Layer 2b,
# the dependency-graph reasoner, on a plan whose risk only shows up when
# resources are looked at together. The scenarios, and what the gate must do
# with each, are listed below and asserted in tests/test_graph_complex.py.
#
#   edge SG (open to the internet, every port)
#     ├── load balancer
#     └── web SG ── web instances (count = 3)
#           │  ╲
#           │   rule app_to_web  (closes a cycle: web SG <-> app SG)
#           │  ╱
#         app SG ── app instances (for_each = api, worker)
#           │
#         db SG ── orders database          4 hops from the edge: OUT of reach
#           ▲
#           └── rule debug_shortcut         ...until this one rule links the
#                                           db SG to the edge SG (2 hops: a
#                                           rule is a link, not a stop)
#
#   analytics database (publicly accessible) ── KMS key ── orders database
#                                           a diamond: a second exposure
#                                           source, 2 hops away
#
#   module "reporting": its own open SG ── lambda ── wildcard IAM policy
#                                           edges inside a child module
#
#   audit bucket + versioning + encryption  a clean island: must stay quiet
#
# What the gate reports on the orders database (weakness 0.92, value 1.00):
#   shortcut only     exposure 0.51  ->  risk 0.47  MEDIUM
#   shared key only   exposure 0.39  ->  risk 0.36  LOW
#   both together     exposure 0.70  ->  risk 0.64  HIGH
# Each case is asserted separately in tests/test_graph_complex.py.
#
# Known gap, kept on purpose: the reporting policy's JSON names the lambda's
# ARN, which is only known after apply, so Terraform leaves the whole policy
# unknown in the plan and the wildcard is not visible to the gate.
#
# The provider uses dummy credentials and skips every AWS API check, so
# `terraform plan` needs no account and costs nothing. Region ap-south-1 is
# approved, so the region rule stays out of the way of the graph findings.
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
    costcenter  = "CC-2077"
  }
  vpc_id  = "vpc-0offline0000000001"
  subnets = ["subnet-0offline000000001", "subnet-0offline000000002"]
}

# --- edge: the only thing that should face the internet --------------------
# VIOLATION: WAF-SEC-004 -- all traffic, every port, from anywhere.
resource "aws_security_group" "edge" {
  name   = "mesh-prod-aps1-edge-sg"
  vpc_id = local.vpc_id

  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = local.tags
}

resource "aws_lb" "public" {
  name               = "mesh-prod-aps1-alb"
  load_balancer_type = "application"
  security_groups    = [aws_security_group.edge.id]
  subnets            = local.subnets
  tags               = local.tags
}

# --- web tier: three identical instances (count) ---------------------------
resource "aws_security_group" "web" {
  name   = "mesh-prod-aps1-web-sg"
  vpc_id = local.vpc_id

  ingress {
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.edge.id]
  }
  tags = local.tags
}

resource "aws_instance" "web" {
  count                  = 3
  ami                    = "ami-0offline000000001"
  instance_type          = "t3.micro"
  subnet_id              = local.subnets[count.index % 2]
  vpc_security_group_ids = [aws_security_group.web.id]
  tags                   = local.tags
}

# --- app tier: two named services (for_each) ------------------------------
resource "aws_security_group" "app" {
  name   = "mesh-prod-aps1-app-sg"
  vpc_id = local.vpc_id

  ingress {
    from_port       = 8080
    to_port         = 8080
    protocol        = "tcp"
    security_groups = [aws_security_group.web.id]
  }
  tags = local.tags
}

resource "aws_instance" "app" {
  for_each               = toset(["api", "worker"])
  ami                    = "ami-0offline000000001"
  instance_type          = "t3.micro"
  subnet_id              = local.subnets[0]
  vpc_security_group_ids = [aws_security_group.app.id]
  tags                   = merge(local.tags, { service = each.key })
}

# Lets the app tier call back into the web tier. It references both groups,
# so the graph now contains a cycle: web SG -> rule -> app SG -> web SG.
resource "aws_security_group_rule" "app_to_web" {
  type                     = "ingress"
  from_port                = 9000
  to_port                  = 9000
  protocol                 = "tcp"
  security_group_id        = aws_security_group.web.id
  source_security_group_id = aws_security_group.app.id
}

# --- data tier -------------------------------------------------------------
resource "aws_security_group" "db" {
  name   = "mesh-prod-aps1-db-sg"
  vpc_id = local.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }
  tags = local.tags
}

# One key encrypts both databases, which links them in the graph.
resource "aws_kms_key" "data" {
  description             = "mesh data key"
  deletion_window_in_days = 7
  enable_key_rotation     = true
  tags                    = local.tags
}

# VIOLATIONS: WAF-SEC-006 plaintext password, WAF-REL-002 no backups.
# Through the tiers it is 4 hops from the edge, beyond the 3-hop reach.
resource "aws_db_instance" "orders" {
  identifier              = "mesh-prod-aps1-orders"
  engine                  = "postgres"
  instance_class          = "db.t3.micro"
  allocated_storage       = 20
  username                = "orders"
  password                = "Orders#2026!"
  backup_retention_period = 0
  skip_final_snapshot     = false
  storage_encrypted       = true
  kms_key_id              = aws_kms_key.data.arn
  vpc_security_group_ids  = [aws_security_group.db.id]
  tags                    = local.tags
}

# The shortcut. A "temporary" debugging rule that lets the edge group reach
# the database group directly. It turns a 4-hop path into a 2-hop one, which
# is exactly the kind of change no single-resource rule can judge.
resource "aws_security_group_rule" "debug_shortcut" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.db.id
  source_security_group_id = aws_security_group.edge.id
}

# VIOLATIONS: publicly accessible (graph exposure), WAF-SEC-006 plaintext
# password. Shares the KMS key with orders: a second exposure source.
resource "aws_db_instance" "analytics" {
  identifier              = "mesh-prod-aps1-analytics"
  engine                  = "postgres"
  instance_class          = "db.t3.micro"
  allocated_storage       = 20
  username                = "analyst"
  password                = "Analytics#2026!"
  backup_retention_period = 7
  skip_final_snapshot     = false
  publicly_accessible     = true
  storage_encrypted       = true
  kms_key_id              = aws_kms_key.data.arn
  tags                    = local.tags
}

# --- reporting: a child module with its own internal graph ----------------
module "reporting" {
  source  = "./modules/reporting"
  vpc_id  = local.vpc_id
  subnets = local.subnets
  tags    = local.tags
}

# --- a clean island: compliant and connected to nothing exposed -----------
resource "aws_s3_bucket" "audit" {
  bucket = "mesh-prod-aps1-audit"
  tags   = local.tags
}

resource "aws_s3_bucket_versioning" "audit" {
  bucket = aws_s3_bucket.audit.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit" {
  bucket = aws_s3_bucket.audit.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = "alias/audit"
    }
  }
}
