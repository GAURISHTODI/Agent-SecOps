# Analytics team: a reporting database that partners query directly, so it is
# publicly accessible. Otherwise it is done properly: AWS manages the password,
# storage is encrypted with the shared key, backups are kept for a week.
# On its own: no weakness, so nothing to combine its exposure with.

variable "kms_key_arn" { type = string }
variable "tags" { type = map(string) }

resource "aws_db_instance" "reporting" {
  identifier                  = "corp-prod-aps1-reporting"
  engine                      = "postgres"
  instance_class              = "db.t3.micro"
  allocated_storage           = 20
  username                    = "reporting"
  manage_master_user_password = true
  backup_retention_period     = 7
  skip_final_snapshot         = false
  publicly_accessible         = true
  storage_encrypted           = true
  kms_key_id                  = var.kms_key_arn
  tags                        = var.tags
}
