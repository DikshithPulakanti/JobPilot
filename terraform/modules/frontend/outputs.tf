output "cloudfront_domain" {
  description = "CloudFront distribution domain (*.cloudfront.net)."
  value       = aws_cloudfront_distribution.jobpilot.domain_name
}

output "cloudfront_id" {
  value = aws_cloudfront_distribution.jobpilot.id
}

output "s3_bucket_id" {
  value = aws_s3_bucket.frontend_assets.id
}
