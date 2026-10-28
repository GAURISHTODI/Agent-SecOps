# Child module of the aws_mesh seeded module. Its resources reference each
# other inside the module, so their plan addresses carry a module prefix
# (module.reporting.*) and the gate has to resolve edges across that prefix.

variable "vpc_id" { type = string }
variable "subnets" { type = list(string) }
variable "tags" { type = map(string) }

# VIOLATION: WAF-SEC-004 -- SSH open to the internet on a function's VPC group.
resource "aws_security_group" "lambda" {
  name   = "mesh-prod-aps1-report-sg"
  vpc_id = var.vpc_id

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = var.tags
}

resource "aws_iam_role" "report" {
  name = "mesh-prod-aps1-report-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
  tags = var.tags
}

resource "aws_lambda_function" "report" {
  function_name = "mesh-prod-aps1-report"
  role          = aws_iam_role.report.arn
  handler       = "index.handler"
  runtime       = "python3.12"
  s3_bucket     = "mesh-prod-aps1-artifacts"
  s3_key        = "report.zip"

  vpc_config {
    subnet_ids         = var.subnets
    security_group_ids = [aws_security_group.lambda.id]
  }
  tags = var.tags
}

# Seeded wildcard actions (CAF-IAM-001) that the gate CANNOT see: the policy
# names the function's ARN, which is unknown until apply, so the whole policy
# document is unknown in the plan. Kept as a documented plan-time blind spot.
resource "aws_iam_role_policy" "report" {
  name = "mesh-prod-aps1-report-policy"
  role = aws_iam_role.report.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "*"
      Resource = [aws_lambda_function.report.arn, "*"]
    }]
  })
}
