# Ledger team: the payments database. Private, so its weaknesses were judged
# acceptable: a password typed into the code (WAF-SEC-006) and one day of
# backups (WAF-REL-002). On its own the graph scores it 0.00 -- nothing can
# reach it. Through the shared security group and key, everything can.

variable "sg_id" { type = string }
variable "kms_key_arn" { type = string }
variable "tags" { type = map(string) }

resource "aws_db_instance" "payments" {
  identifier              = "corp-prod-aps1-payments"
  engine                  = "postgres"
  instance_class          = "db.t3.micro"
  allocated_storage       = 20
  username                = "ledger"
  password                = "Ledger#2026!"
  backup_retention_period = 1
  skip_final_snapshot     = false
  publicly_accessible     = false
  storage_encrypted       = true
  kms_key_id              = var.kms_key_arn
  vpc_security_group_ids  = [var.sg_id]
  tags                    = var.tags
}
