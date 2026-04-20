output "rds_endpoint" {
  description = "RDS hostname (address)."
  value       = aws_db_instance.jobpilot.address
}

output "rds_port" {
  value = aws_db_instance.jobpilot.port
}

output "db_name" {
  value = var.db_name
}

output "db_username" {
  value = var.db_username
}
