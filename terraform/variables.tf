variable "aws_region" {
  description = "AWS region for all resources."
  type        = string
  default     = "us-east-1"
}

variable "your_ip" {
  description = "Your public IPv4 address in CIDR form for SSH (e.g. 203.0.113.10/32)."
  type        = string
}

variable "db_username" {
  description = "RDS master username."
  type        = string
  default     = "jobpilot"
}

variable "db_name" {
  description = "RDS database name."
  type        = string
  default     = "jobpilot"
}

variable "db_password" {
  description = "RDS master password (also stored in SSM at /jobpilot/db_password)."
  type        = string
  sensitive   = true
}

variable "anthropic_api_key" {
  description = "Anthropic API key (stored in SSM)."
  type        = string
  sensitive   = true
}

variable "openai_api_key" {
  description = "OpenAI API key (stored in SSM)."
  type        = string
  sensitive   = true
}

variable "github_token" {
  description = "GitHub personal access token for cloning the repo (stored in SSM)."
  type        = string
  sensitive   = true
}

variable "ec2_instance_type" {
  description = "EC2 instance type for the JobPilot backend host."
  type        = string
  default     = "t3.medium"
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t3.micro"
}
