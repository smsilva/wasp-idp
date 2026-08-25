output "role_arn" {
  description = "ARN do role assumido pela service account."
  value       = aws_iam_role.this.arn
}

output "role_name" {
  description = "Nome do role, para anexar policies extras fora do modulo."
  value       = aws_iam_role.this.name
}
