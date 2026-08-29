output "namespace" {
  description = "Namespace onde o controller roda."
  value       = var.namespace
}

output "service_account_name" {
  description = "Service account do controller, alvo da Pod Identity association."
  value       = var.service_account_name
}
