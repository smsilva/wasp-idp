output "namespace" {
  description = "Namespace do Crossplane."
  value       = var.namespace
}

output "service_account_name" {
  description = "Service account do core, alvo da Pod Identity association."
  value       = var.service_account_name
}
