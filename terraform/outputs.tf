output "ec2_public_ip" {
  description = "Elastic IP attached to JobPilot EC2."
  value       = module.backend.elastic_ip
}

output "ec2_public_dns" {
  description = "Public DNS of the JobPilot EC2 instance."
  value       = module.backend.ec2_public_dns
}

output "rds_endpoint" {
  description = "RDS hostname."
  value       = module.database.rds_endpoint
}

output "cloudfront_domain" {
  description = "CloudFront distribution domain name."
  value       = module.frontend.cloudfront_domain
}

output "backend_url" {
  description = "Direct FastAPI URL on the Elastic IP."
  value       = "http://${module.backend.elastic_ip}:8000"
}

output "frontend_url" {
  description = "HTTPS URL via CloudFront (Next.js default; /api* and /events proxy to FastAPI)."
  value       = "https://${module.frontend.cloudfront_domain}"
}
