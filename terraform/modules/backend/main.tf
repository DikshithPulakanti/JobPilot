data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_eip" "backend" {
  domain = "vpc"

  tags = {
    Name = "jobpilot-backend-eip"
  }
}

resource "aws_instance" "backend" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.ec2_instance_type
  subnet_id              = var.public_subnet_id
  vpc_security_group_ids = [var.backend_security_group_id]
  iam_instance_profile   = var.iam_instance_profile_name

  user_data = base64encode(
    templatefile("${path.module}/user_data.sh.tpl", {
      aws_region  = var.aws_region
      rds_address = var.rds_address
      db_username = var.db_username
      db_name     = var.db_name
      elastic_ip  = aws_eip.backend.public_ip
    })
  )

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
  }

  tags = {
    Name = "jobpilot-backend"
  }
}

resource "aws_eip_association" "backend" {
  instance_id   = aws_instance.backend.id
  allocation_id = aws_eip.backend.id
}
