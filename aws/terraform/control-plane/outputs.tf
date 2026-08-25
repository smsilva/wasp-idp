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
