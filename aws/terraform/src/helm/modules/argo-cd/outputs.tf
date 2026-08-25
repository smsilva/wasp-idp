output "namespace" {
  description = "Namespace do ArgoCD."
  value       = var.namespace
}

output "server_service_name" {
  description = "Service do server, alvo do port-forward."
  value       = "argo-cd-argocd-server"
}

output "admin_password_command" {
  description = "Comando que recupera a senha inicial do admin (break-glass)."
  value       = "kubectl -n ${var.namespace} get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d"
}
