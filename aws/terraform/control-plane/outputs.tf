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

output "cell_ingress_fqdn" {
  description = <<-EOT
    O wildcard desta celula. O aceite do 3.2 e um curl em
    app.<esta celula>.<subzona> DA INTERNET, sem tunel, com TLS valido.
  EOT
  value       = local.cell_wildcard
}

output "cell_certificate_arn" {
  description = "Certificado da celula, anexado ao listener :443 compartilhado por SNI. Sai do validation, nao do certificate — e o unico que espera a validacao."
  value       = aws_acm_certificate_validation.cell.certificate_arn
}

output "hub_target_group_arn" {
  description = "Target group do lado HUB, na conta network, apontando para os enderecos fixos do NLB da spoke. Nome gerado por name_prefix, entao o ARN muda a cada recriacao — ler daqui, nunca fixar."
  value       = aws_lb_target_group.hub_to_cell.arn
}

output "hub_listener_rule_priority" {
  description = "Priority da rule desta celula no listener compartilhado. Derivada do nome; colisao entre celulas falha alto no apply, o que e o comportamento desejado."
  value       = local.listener_rule_priority
}
