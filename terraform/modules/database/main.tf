resource "aws_db_subnet_group" "jobpilot" {
  name       = "jobpilot-db-subnet"
  subnet_ids = var.private_subnet_ids

  tags = {
    Name = "jobpilot-db-subnet"
  }
}

resource "aws_db_instance" "jobpilot" {
  identifier             = "jobpilot-pg"
  engine                 = "postgres"
  engine_version         = "15"
  instance_class         = var.db_instance_class
  allocated_storage      = 20
  storage_type           = "gp2"
  db_name                = var.db_name
  username               = var.db_username
  password               = var.db_password
  db_subnet_group_name   = aws_db_subnet_group.jobpilot.name
  vpc_security_group_ids = [var.rds_security_group_id]
  multi_az               = false
  deletion_protection    = false
  skip_final_snapshot    = true
  publicly_accessible    = false

  tags = {
    Name = "jobpilot-rds"
  }
}

locals {
  schema_file = var.schema_sql_path != "" ? var.schema_sql_path : "${path.root}/../backend/tracker/schema.sql"
}

resource "null_resource" "apply_schema" {
  depends_on = [aws_db_instance.jobpilot]

  triggers = {
    endpoint = aws_db_instance.jobpilot.address
    password = sha256(var.db_password)
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -e
      export AWS_DEFAULT_REGION=${var.aws_region}
      PGPASSWORD="$(aws ssm get-parameter --name /jobpilot/db_password --with-decryption --query Parameter.Value --output text)"
      export PGPASSWORD
      psql "postgresql://${var.db_username}:$PGPASSWORD@${aws_db_instance.jobpilot.address}:5432/${var.db_name}" -f "${local.schema_file}"
    EOT
  }
}
