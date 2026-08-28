output "cluster_name" {
  description = "Nome do cluster da celula."
  value       = module.cluster.cluster_name
}

output "region" {
  description = "Regiao da celula."
  value       = var.region
}

output "argocd_namespace" {
  description = "Namespace do ArgoCD."
  value       = local.install_argocd ? module.argo_cd[0].namespace : null
}

output "eso_namespace" {
  description = "Namespace do External Secrets."
  value       = local.install_external_secrets ? module.external_secrets[0].namespace : null
}

output "crossplane_namespace" {
  description = "Namespace do Crossplane."
  value       = local.install_crossplane ? module.crossplane[0].namespace : null
}

output "kubeconfig_command" {
  description = "Comando que escreve o contexto deste cluster no kubeconfig local."
  value       = "aws eks update-kubeconfig --name ${module.cluster.cluster_name} --region ${var.region} --profile ${var.aws_profile}"
}

# --------------------------------------------------------------------------------------
# 3.1 — a interface com a fase 3.2 (lado hub). Os dois valores sao calculados, nao lidos
# do recurso, entao a 3.2 pode ser escrita antes de o NLB existir.
# --------------------------------------------------------------------------------------

output "ingress_private_ips" {
  description = "Enderecos fixos do NLB interno, um por AZ. E o que a target group do hub registra."
  value       = module.ingress.private_ips
}

output "ingress_target_group_arn" {
  description = "ARN da target group do gateway. Mesmo valor que o ConfigMap entrega ao GitOps."
  value       = module.ingress.target_group_arn
}

output "ingress_security_group_id" {
  description = "SG do NLB interno. Origem das regras que o SG do cluster autoriza."
  value       = module.ingress.security_group_id
}
