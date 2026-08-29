output "gateway_namespace" {
  description = "Namespace do ingress gateway. Metade do serviceRef do TargetGroupBinding."
  value       = var.gateway_namespace
}

output "gateway_service_name" {
  description = "Nome do Service do gateway — o mesmo do release. A outra metade do serviceRef."
  value       = var.gateway_release_name
}

output "gateway_selector" {
  description = <<-EOT
    Valor do rótulo `istio:` nos pods do gateway, que é o que o `Gateway` CR seleciona. O chart
    tira o prefixo `istio-` do nome do release ao montá-lo: `istio-ingress` vira `ingress`.
  EOT
  value       = local.gateway_selector
}

output "gateway_ref" {
  description = <<-EOT
    Referência do `Gateway` CR no formato `<namespace>/<nome>`, que é a forma que um
    VirtualService de OUTRO namespace tem de usar. Só o nome curto resolveria no namespace do
    próprio VirtualService, onde o Gateway não está.
  EOT
  value       = "${var.gateway_namespace}/${var.gateway_cr_name}"
}

output "gateway_hosts" {
  description = <<-EOT
    Hosts que o `Gateway` CR aceita. Existe para que a camada que compõe a célula possa ASSERIR
    que eles são o mesmo wildcard do certificado do ACM e da listener rule do ALB — input de
    módulo não é assertável de fora, output é.
  EOT
  value       = var.gateway_hosts
}
