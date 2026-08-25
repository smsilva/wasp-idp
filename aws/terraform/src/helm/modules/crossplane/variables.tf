variable "chart_version" {
  description = "Versao do chart crossplane. Canal stable, nao master (que publica RCs)."
  type        = string
  default     = "2.4.0"
}

variable "namespace" {
  description = "Namespace do Crossplane."
  type        = string
  default     = "crossplane-system"
}

variable "service_account_name" {
  description = "Service account do core. Deve casar com a Pod Identity association."
  type        = string
  default     = "crossplane"
}

variable "extra_values" {
  description = "YAML adicional mesclado ao values base."
  type        = string
  default     = ""
}
