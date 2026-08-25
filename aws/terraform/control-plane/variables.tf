variable "name" {
  description = "Nome da celula. Prefixo de todos os recursos."
  type        = string
  default     = "control-plane"
}

variable "region" {
  description = "Regiao AWS da celula."
  type        = string
}

variable "aws_profile" {
  description = "Profile local com acesso a conta cicd."
  type        = string
}

variable "network_profile" {
  description = "Profile local com acesso de leitura a conta network, dona da VPC hub."
  type        = string
  default     = "network"
}

variable "hub_vpc_name" {
  description = "Valor da tag Name da VPC hub criada pela camada 1. O modulo src/network sufixa -vpc no name do root, que em us-east-1 e poc-hub."
  type        = string
  default     = "poc-hub-vpc"
}

variable "vpc_cidr" {
  description = "CIDR da VPC spoke. Um /16 dentro do supernet 10.0.0.0/12."
  type        = string

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0)) && startswith(var.vpc_cidr, "10.") && can(tonumber(split(".", var.vpc_cidr)[1])) && tonumber(split(".", var.vpc_cidr)[1]) >= 0 && tonumber(split(".", var.vpc_cidr)[1]) <= 15
    error_message = "o CIDR deve ser um /16 dentro do supernet 10.0.0.0/12 (10.0 a 10.15), recebido ${var.vpc_cidr}."
  }
}

variable "availability_zones" {
  description = "Duas zonas de disponibilidade da regiao."
  type        = list(string)
}

variable "enable_nat_gateway" {
  description = "NAT na spoke. Sem TGW nao ha egress pelo hub — os nos dependem disto."
  type        = bool
  default     = true
}

variable "kubernetes_version" {
  description = "Versao do Kubernetes."
  type        = string
  default     = "1.34"
}

variable "network_account_id" {
  description = "Conta que hospeda a VPC hub. Publicado no platform-bootstrap."
  type        = string
}

variable "target_account_ids" {
  description = "Contas onde o Crossplane cria recursos, via assume role."
  type        = list(string)
}

variable "access_entries" {
  description = "Principals IAM com acesso ao cluster, alem do criador."
  type = map(object({
    principal_arn = string
    policy_arn    = string
    access_scope  = optional(string, "cluster")
  }))
  default = {}
}
