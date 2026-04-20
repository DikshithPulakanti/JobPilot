output "elastic_ip" {
  description = "Elastic IP attached to the JobPilot EC2 instance."
  value       = aws_eip.backend.public_ip
}

output "ec2_public_dns" {
  description = "Public DNS hostname of the EC2 instance."
  value       = aws_instance.backend.public_dns
}

output "ec2_instance_id" {
  value = aws_instance.backend.id
}
