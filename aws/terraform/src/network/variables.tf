variable "name" {
  description = "Nome base dos recursos: <name>-vpc, <name>-public-<az>, <name>-rt-private, ..."
  type        = string
}

variable "vpc_cidr" {
  description = <<-EOT
    CIDR da VPC — um /16 do supernet 10.0.0.0/12 (ver aws/docs/network/01-cidr-addressing.md).
    As subnets são DERIVADAS deste valor com cidrsubnet(), nunca fixas.
  EOT
  type        = string

  validation {
    # Precisa caber 2 * length(availability_zones) subnets de (prefixo + subnet_newbits).
    # Com os defaults (2 AZs, newbits 4) o teto é /20 — um /24 não serve.
    condition     = can(cidrhost(var.vpc_cidr, 0)) && tonumber(split("/", var.vpc_cidr)[1]) <= 20
    error_message = "vpc_cidr deve ser um CIDR válido com prefixo /20 ou maior (ex.: 10.1.0.0/16)."
  }
}

variable "availability_zones" {
  description = <<-EOT
    Exatamente 2 AZs. O EKS exige 2 distintas, e a lista de subnets do control plane é
    IMUTÁVEL depois de criado o cluster — mudar aqui depois é recriar o cluster.
  EOT
  type        = list(string)

  validation {
    condition     = length(var.availability_zones) == 2
    error_message = "availability_zones deve conter exatamente 2 AZs."
  }

  validation {
    condition     = length(distinct(var.availability_zones)) == length(var.availability_zones)
    error_message = "as AZs devem ser distintas."
  }
}

variable "subnet_newbits" {
  description = <<-EOT
    Bits somados ao prefixo da VPC para cada subnet. 4 sobre um /16 dá /20 (4094 IPs úteis),
    consumindo 4 dos 16 blocos e deixando 12 livres. /24 seria pequeno para EKS: o VPC CNI
    tira o IP do pod da subnet do nó.
  EOT
  type        = number
  default     = 4
}

variable "enable_nat_gateway" {
  description = <<-EOT
    NAT Gateway + EIP + rota default na route table privada. Desligado, as subnets privadas
    ficam sem saída para a internet. A VPC hub não precisa enquanto não houver TGW — nada
    roteia por ela, e o NAT custaria ~US$ 32/mês servindo zero tráfego.
  EOT
  type        = bool
  default     = true
}

variable "tags" {
  description = "Tags adicionais, mescladas ao Name de cada recurso."
  type        = map(string)
  default     = {}
}
