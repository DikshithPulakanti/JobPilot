variable "aws_region" {
  type = string
}

variable "public_subnet_id" {
  type = string
}

variable "backend_security_group_id" {
  type = string
}

variable "ec2_instance_type" {
  type = string
}

variable "iam_instance_profile_name" {
  type = string
}

variable "rds_address" {
  description = "RDS hostname from aws_db_instance.address."
  type        = string
}

variable "db_username" {
  type = string
}

variable "db_name" {
  type = string
}
