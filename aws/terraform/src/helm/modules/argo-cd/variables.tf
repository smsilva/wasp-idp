variable "chart_version" {
  description = "Versao do chart argo-cd. 10.4.0 entrega o ArgoCD 3.5.1."
  type        = string
  default     = "10.4.0"
}

variable "namespace" {
  description = "Namespace do ArgoCD."
  type        = string
  default     = "argocd"
}

variable "server_url" {
  description = "URL externa do ArgoCD. Com port-forward, localhost."
  type        = string
  default     = "http://localhost:8080"
}

variable "oidc_enabled" {
  description = "Emitir a configuracao de OIDC. Exige o client secret ja no Secrets Manager."
  type        = bool
  default     = false
}

variable "oidc_name" {
  description = "Nome do provedor OIDC. Compoe a chave do placeholder oidc.<nome>.clientSecret."
  type        = string
  default     = "google"
}

variable "oidc_issuer" {
  description = "Issuer OIDC."
  type        = string
  default     = ""
}

variable "oidc_client_id" {
  description = "Client id OIDC. Nao e segredo."
  type        = string
  default     = ""
}

variable "extra_values" {
  description = "YAML adicional mesclado ao values base."
  type        = string
  default     = ""
}
