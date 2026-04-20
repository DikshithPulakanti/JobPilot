output "vpc_id" {
  value = aws_vpc.main.id
}

output "public_subnet_ids" {
  value = [aws_subnet.public_a.id, aws_subnet.public_b.id]
}

output "private_subnet_ids" {
  value = [aws_subnet.private_a.id, aws_subnet.private_b.id]
}

output "sg_backend_id" {
  value = aws_security_group.backend.id
}

output "sg_rds_id" {
  value = aws_security_group.rds.id
}
