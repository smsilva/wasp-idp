variable "name" {
  description = "Nome do cluster EKS."
  type        = string
}

variable "kubernetes_version" {
  description = "Versao do Kubernetes do control plane. Default = versao default do EKS em 2026-08-25; conferir com 'aws eks describe-cluster-versions' antes de criar cluster novo."
  type        = string
  default     = "1.36"
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
  description = <<-EOT
    CIDRs autorizados no endpoint publico. A AWS le lista VAZIA como 0.0.0.0/0 — por isso
    vazio e recusado quando o endpoint publico esta ligado: omitir um valor nao pode ser o
    caminho para expor a API do cluster ao mundo.
  EOT
  type        = list(string)
  default     = []

  validation {
    # Com o endpoint publico desligado a lista e irrelevante e vazia esta correta; a
    # invariante so morde quando ha endpoint publico para restringir.
    condition     = !var.endpoint_public_access || length(var.public_access_cidrs) > 0
    error_message = "com endpoint_public_access ligado, public_access_cidrs nao pode ser vazio: a AWS interpreta lista vazia como 0.0.0.0/0."
  }

  validation {
    # alltrue([]) e true, e aqui esta certo: lista vazia ja e tratada pela validacao acima.
    condition     = alltrue([for cidr in var.public_access_cidrs : can(cidrhost(cidr, 0))])
    error_message = "todo item de public_access_cidrs deve ser um CIDR com prefixo (ex.: 203.0.113.10/32)."
  }
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
