output "cluster_name" {
  description = "Nome do cluster."
  value       = aws_eks_cluster.this.name
}

output "cluster_endpoint" {
  description = "Endpoint da API do Kubernetes."
  value       = aws_eks_cluster.this.endpoint
}

output "cluster_ca_data" {
  description = "CA do cluster em base64, para configurar os providers kubernetes/helm."
  value       = aws_eks_cluster.this.certificate_authority[0].data
}

output "cluster_security_group_id" {
  description = "Security group gerenciado pelo EKS."
  value       = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
}

# Le do RECURSO, nao da variavel: e o unico jeito de um teste do root provar que o valor
# atravessou o modulo e chegou ao vpc_config, em vez de so provar que foi passado.
output "public_access_cidrs" {
  description = "CIDRs efetivamente autorizados no endpoint publico da API."
  value       = aws_eks_cluster.this.vpc_config[0].public_access_cidrs
}

output "node_role_arn" {
  description = "Role compartilhado pelos node groups."
  value       = aws_iam_role.node.arn
}

output "oidc_issuer_url" {
  description = "Issuer OIDC do cluster. Nao usado por Pod Identity; fica para IRSA de terceiros."
  value       = aws_eks_cluster.this.identity[0].oidc[0].issuer
}
