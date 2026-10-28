# Storefront team: three healthy web servers, each with a public IP.
# On its own: only MEDIUM notes (CAF-LZ-003, public IP without justification).

variable "sg_id" { type = string }
variable "subnet" { type = string }
variable "tags" { type = map(string) }

resource "aws_instance" "web" {
  count                  = 3
  ami                    = "ami-0offline000000003"
  instance_type          = "t3.micro"
  subnet_id              = var.subnet
  vpc_security_group_ids = [var.sg_id]
  tags                   = var.tags
}

resource "aws_eip" "web" {
  count    = 3
  domain   = "vpc"
  instance = aws_instance.web[count.index].id
  tags     = var.tags
}
