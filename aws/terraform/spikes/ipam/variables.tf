variable "management_profile" {
  description = "Profile da conta management da Organization. So delega o IPAM admin — nao pode ser o IPAM account (regra do servico)."
  type        = string
  default     = "personal"
}

variable "network_profile" {
  description = "Profile da conta `network` (Connectivity Account), que sera o IPAM delegated admin e dona do IPAM."
  type        = string
  default     = "network"
}

variable "spoke_profile" {
  description = "Profile de uma conta spoke, usada para provar alocacao cross-account a partir do pool compartilhado por RAM."
  type        = string
  default     = "cicd"
}

variable "region" {
  description = "Home region do IPAM. Tem de ser uma das operating_regions."
  type        = string
  default     = "us-east-1"

  validation {
    condition     = contains(["us-east-1", "us-west-2"], var.region)
    error_message = "a home region tem de ser uma regiao onde este repo opera (us-east-1 ou us-west-2)."
  }
}

variable "supernet" {
  description = "Supernet do escopo privado — o mesmo bloco do ADR 0003, para que o auto_import adote as VPCs existentes."
  type        = string
  default     = "10.0.0.0/12"

  validation {
    condition     = can(cidrhost(var.supernet, 0))
    error_message = "supernet deve ser um CIDR valido com prefixo (ex.: 10.0.0.0/12)."
  }
}

variable "regional_blocks" {
  description = <<-EOT
    Um bloco /14 contiguo por regiao, conforme o ADR 0003 amendado. Contiguidade nao e estetica: o
    pool regional exige `locale`, e locale e IMUTAVEL — plano alocado por ordem de criacao nao tem
    bloco contiguo por regiao e obrigaria a re-enderecar VPC na adocao.
  EOT
  type        = map(string)
  default = {
    "us-east-1" = "10.0.0.0/14"
    "us-west-2" = "10.4.0.0/14"
  }

  validation {
    condition     = alltrue([for cidr in values(var.regional_blocks) : can(cidrhost(cidr, 0))])
    error_message = "todo bloco regional deve ser um CIDR valido com prefixo."
  }

  validation {
    condition     = length(var.regional_blocks) == length(distinct(values(var.regional_blocks)))
    error_message = "duas regioes nao podem receber o mesmo bloco — e exatamente a colisao que este spike investiga."
  }
}

variable "organization_reserved_block" {
  description = <<-EOT
    Bloco reservado a Organization (N=0). Nao tem recurso, entao entra por alocacao EXPLICITA, nao
    por auto_import. `null` desliga — necessario quando o pool regional nao contem este bloco (o
    N=0 vive no /14 de us-east-1, entao um teste em us-west-2 tem de desligar).
  EOT
  type        = string
  default     = "10.0.0.0/16"
}

variable "proof_vpc_omit_tag" {
  description = <<-EOT
    Quando true, a VPC de prova nasce SEM a tag exigida pelo pool. E a prova negativa: o apply tem
    de FALHAR. Serve para demonstrar que `allocation_resource_tags` e condicao de alocacao, nao
    convencao — a unica coisa que separa IPAM de planilha.
  EOT
  type        = bool
  default     = false
}

variable "allocation_tag_key" {
  description = "Tag exigida para alocar do pool regional. Transforma 'cada celula declara seu dono' de convencao em condicao de alocacao."
  type        = string
  default     = "cell"
}

variable "proof_vpc_netmask_length" {
  description = "Tamanho pedido pela VPC de prova. Ela pede TAMANHO, nao CIDR — que e o ponto inteiro do IPAM."
  type        = number
  default     = 24

  validation {
    condition     = var.proof_vpc_netmask_length >= 16 && var.proof_vpc_netmask_length <= 28
    error_message = "netmask da VPC de prova deve estar entre /16 e /28."
  }
}
