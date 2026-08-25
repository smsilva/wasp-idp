variable "cluster_name" {
  description = "Cluster EKS que recebe os node groups."
  type        = string
}

variable "node_role_arn" {
  description = "Role IAM compartilhado pelos nos, vindo do modulo cluster."
  type        = string
}

variable "subnet_ids" {
  description = "Subnets dos nos. Apenas privadas."
  type        = list(string)
}

variable "node_groups" {
  description = "Node groups a criar. A chave vira sufixo do nome."
  type = map(object({
    instance_types = optional(list(string), ["t3.medium"])
    capacity_type  = optional(string, "ON_DEMAND")
    desired_size   = optional(number, 2)
    min_size       = optional(number, 2)
    max_size       = optional(number, 4)
    labels         = optional(map(string), {})
  }))
  default = {
    default = {}
  }

  validation {
    condition = alltrue([
      for group in var.node_groups : contains(["ON_DEMAND", "SPOT"], group.capacity_type)
    ])
    error_message = "capacity_type so aceita ON_DEMAND ou SPOT, recebido ${join(",", [for group in var.node_groups : group.capacity_type])}."
  }
}

variable "tags" {
  description = "Tags aplicadas aos recursos do modulo."
  type        = map(string)
  default     = {}
}
