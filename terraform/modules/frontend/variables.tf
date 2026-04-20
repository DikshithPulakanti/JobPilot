variable "ec2_public_dns" {
  description = "EC2 public DNS hostname (used as CloudFront custom origin domain)."
  type        = string
}

variable "s3_bucket_name" {
  description = "Globally unique S3 bucket name for static assets."
  type        = string
  default     = "jobpilot-frontend-static"
}
