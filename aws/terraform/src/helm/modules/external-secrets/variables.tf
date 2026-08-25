variable "chart_version" {
  description = "Versao do chart external-secrets."
  type        = string
  default     = "2.9.0"
}

variable "namespace" {
  description = "Namespace do External Secrets Operator."
  type        = string
  default     = "external-secrets"
}

variable "service_account_name" {
  description = "Service account do controller. Deve casar com a Pod Identity association."
  type        = string
  default     = "external-secrets"
}

variable "extra_values" {
  description = "YAML adicional mesclado ao values base."
  type        = string
  default     = ""
}
