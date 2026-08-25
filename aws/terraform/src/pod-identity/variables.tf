variable "name" {
  description = "Nome do role IAM. Deve ser unico na conta."
  type        = string
}

variable "cluster_name" {
  description = "Nome do cluster EKS onde a association vale."
  type        = string
}

variable "namespace" {
  description = "Namespace Kubernetes da service account."
  type        = string
}

variable "service_account_name" {
  description = "Nome da service account que assume o role."
  type        = string
}

variable "policy_json" {
  description = "Policy inline em JSON. Null quando so ha managed policies."
  type        = string
  default     = null
}

variable "managed_policy_arns" {
  description = "ARNs de managed policies a anexar ao role."
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Tags aplicadas aos recursos do modulo."
  type        = map(string)
  default     = {}
}
