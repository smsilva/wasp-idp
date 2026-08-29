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
