variable "cluster_name" {
  description = "Nome do cluster EKS. Vai explícito para o chart — o controller não deve descobrí-lo por IMDS."
  type        = string
}

variable "region" {
  description = "Região do cluster. Explícita pelo mesmo motivo de cluster_name."
  type        = string
}

variable "vpc_id" {
  description = "VPC do cluster. Explícita pelo mesmo motivo de cluster_name."
  type        = string
}

variable "chart_version" {
  description = "Versão do chart aws-load-balancer-controller."
  type        = string
  default     = "3.5.0"
}

variable "namespace" {
  description = "Namespace do controller. Deve casar com a Pod Identity association."
  type        = string
  default     = "kube-system"
}

variable "service_account_name" {
  description = "Service account do controller. Deve casar com a Pod Identity association."
  type        = string
  default     = "aws-load-balancer-controller"
}

variable "extra_values" {
  description = "YAML adicional mesclado ao values base."
  type        = string
  default     = ""
}
