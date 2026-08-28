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

variable "endpoint_public_access" {
  description = <<-EOT
    Expor o endpoint da API do EKS na internet. DEFAULT false — este e o 2.5.

    Fechado, o caminho ate a API e o privado: tunel do Client VPN -> TGW -> ENI do endpoint
    na VPC spoke. Quem depende disto NAO e so o operador: os providers helm e kubernetes
    falam com o API server a partir da maquina que roda o apply, entao um apply sem tunel
    conectado nao completa. E o preco consciente da postura privada.

    Ligar e break-glass, e exige public_access_cidrs junto (o modulo recusa lista vazia com
    o endpoint aberto). Ato visivel em diff, nao valor esquecido num tfvars.
  EOT
  type        = bool
  default     = false
}

variable "public_access_cidrs" {
  description = <<-EOT
    CIDRs autorizados no endpoint publico da API do EKS. So tem efeito com
    endpoint_public_access = true; com o endpoint fechado o modulo OMITE o atributo em vez de
    mandar lista vazia (mandar vazia daria perpetual diff contra o 0.0.0.0/0 que a EKS guarda
    como default).

    O default vazio aqui NAO reabre o Known Broken 3: a lista vazia so e alcancavel com o
    endpoint publico desligado. Com ele ligado, quem recusa vazio e o modulo src/cluster,
    onde mora a semantica da AWS ("vazio significa o mundo"). scripts/generate-tfvars
    descobre o IP publico corrente quando a descoberta e pedida.
  EOT
  type        = list(string)
  default     = []

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

variable "base_domain" {
  description = <<-EOT
    Dominio raiz sob o qual a camada 02 delegou a subzona. Compoe o FQDN do certificado desta
    celula: *.<name>.<subzone_label>.<base_domain>.

    SEM DEFAULT de proposito, mesma razao da connectivity/: e valor por-conta num repo publico,
    e a ausencia invalida qualquer terraform.tfvars ja gerado — quem aplicar tem de regenerar
    (./scripts/generate-tfvars --force) em vez de herdar um valor de outra conta.
  EOT
  type        = string

  validation {
    condition     = length(var.base_domain) > 0 && !endswith(var.base_domain, ".") && length(split(".", var.base_domain)) >= 2
    error_message = "base_domain deve ser um dominio sem ponto final, com ao menos dois labels, recebido ${var.base_domain}."
  }
}

variable "subzone_label" {
  description = "Label da subzona delegada pela camada 02. `sandbox` NAO e ambiente de teste — o de teste e nonprod."
  type        = string
  default     = "nonprod"
}

variable "hub_alb_name" {
  description = <<-EOT
    Nome do ALB de ingress que a camada 03 cria (`<nome do hub>-ingress`). Lido por data
    source, nao por terraform_remote_state — mesmo padrao da VPC hub e do TGW.

    E um segundo lugar que codifica o nome do hub, ao lado de hub_vpc_name e da tag do TGW
    (hoje literal no main.tf). Unificar os tres num `hub_name` seria melhor e nao foi feito
    aqui para nao arrastar mudanca de variavel existente para dentro do 3.2.
  EOT
  type        = string
  default     = "poc-hub-ingress"
}
