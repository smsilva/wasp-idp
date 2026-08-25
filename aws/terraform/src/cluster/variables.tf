variable "name" {
  description = "Nome do cluster EKS."
  type        = string
}

variable "kubernetes_version" {
  description = "Versao do Kubernetes do control plane."
  type        = string
  default     = "1.34"
}

variable "subnet_ids" {
  description = "Subnets do control plane. Publicas + privadas; imutavel apos a criacao."
  type        = list(string)

  validation {
    condition     = length(var.subnet_ids) >= 2
    error_message = "o EKS exige subnets em pelo menos 2 zonas de disponibilidade, recebidas ${length(var.subnet_ids)}."
  }
}

variable "endpoint_public_access" {
  description = "Expor o endpoint da API na internet."
  type        = bool
  default     = true
}

variable "endpoint_private_access" {
  description = "Expor o endpoint da API dentro da VPC."
  type        = bool
  default     = true
}

variable "public_access_cidrs" {
  description = "CIDRs autorizados no endpoint publico. Vazio significa 0.0.0.0/0."
  type        = list(string)
  default     = []
}

variable "access_entries" {
  description = "Principals IAM com acesso ao cluster, alem do criador. Chave e um rotulo livre."
  type = map(object({
    principal_arn = string
    policy_arn    = string
    access_scope  = optional(string, "cluster")
  }))
  default = {}
}

variable "tags" {
  description = "Tags aplicadas aos recursos do modulo."
  type        = map(string)
  default     = {}
}
