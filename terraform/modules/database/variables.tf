variable "aws_region" {
  type = string
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnets for RDS subnet group."
}

variable "rds_security_group_id" {
  type = string
}

variable "db_name" {
  type = string
}

variable "db_username" {
  type = string
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "db_instance_class" {
  type = string
}

variable "schema_sql_path" {
  description = "Absolute path to schema.sql for local-exec (defaults to repo backend/tracker/schema.sql)."
  type        = string
  default     = ""
}
