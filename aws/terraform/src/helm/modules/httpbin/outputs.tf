output "namespace" {
  description = "Namespace do workload de prova."
  value       = var.namespace
}

output "url" {
  description = "URL pública que deve responder 200 com TLS válido quando a célula está inteira."
  value       = "https://${var.host}/"
}
