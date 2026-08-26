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
  description = "Versao do Kubernetes. O terraform.tfvars gerado por scripts/generate-tfvars sobrescreve com a versao default do EKS descoberta na hora."
  type        = string
  default     = "1.36"
}

variable "network_account_id" {
  description = "Conta que hospeda a VPC hub. Publicado no platform-bootstrap."
  type        = string
}

variable "target_account_ids" {
  description = "Contas onde o Crossplane cria recursos, via assume role."
  type        = list(string)
}

variable "public_access_cidrs" {
  description = <<-EOT
    CIDRs autorizados no endpoint publico da API do EKS. SEM DEFAULT de proposito: quem fala
    com o API server e a maquina que roda o terraform apply, entao o valor certo depende de
    onde o apply roda e nao ha default seguro. scripts/generate-tfvars descobre o IP publico
    corrente e escreve o /32.

    Some quando o 2.5 fechar o endpoint publico; ate lah e o unico controle de quem alcanca
    a API.
  EOT
  type        = list(string)

  validation {
    condition     = length(var.public_access_cidrs) > 0
    error_message = "public_access_cidrs nao pode ser vazio: a AWS le lista vazia como 0.0.0.0/0. Rode scripts/generate-tfvars para descobrir o IP corrente."
  }

  validation {
    # A checagem de CIDR valido mora no modulo. Aqui mora a POLITICA da celula: nem por
    # engano nem de proposito esta camada expoe a API do cluster ao mundo. Abrir de verdade
    # exige editar esta validacao, que e ato visivel em diff — nao um valor num tfvars
    # gitignored.
    condition     = !contains(var.public_access_cidrs, "0.0.0.0/0")
    error_message = "0.0.0.0/0 em public_access_cidrs: a celula control-plane nao expoe a API do EKS ao mundo (ver Known Broken 3 no HANDOFF)."
  }
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
