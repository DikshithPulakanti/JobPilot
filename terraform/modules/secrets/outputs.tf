output "ec2_instance_profile_name" {
  description = "Instance profile name for EC2."
  value       = aws_iam_instance_profile.jobpilot_ec2.name
}

output "ec2_instance_profile_arn" {
  value = aws_iam_instance_profile.jobpilot_ec2.arn
}

output "ec2_role_name" {
  value = aws_iam_role.jobpilot_ec2.name
}

output "cloudwatch_log_group_name" {
  value = aws_cloudwatch_log_group.backend.name
}
