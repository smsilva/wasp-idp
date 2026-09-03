variable "name" {
  description = "Nome do hub. Prefixo de todos os recursos e base das tags de descoberta."
  type        = string
  default     = "poc-hub"
}

variable "region" {
  description = <<-EOT
    A regiao do hub. NAO configura provider — o provider vem da raiz. Serve para compor os nomes
    que vivem em namespace GLOBAL: o aws_iam_saml_provider (IAM e global por conta) e o FQDN do
    endpoint da VPN (a subzona do Route 53 e uma so para a Organization inteira).

    Sem isto, a segunda regiao falha com EntityAlreadyExists no SAML provider e SOBRESCREVE o
    record vpn.<subzona> da primeira — o segundo em silencio, que e o pior dos dois.
  EOT
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR da VPC hub. Um /16 dentro do supernet 10.0.0.0/12 — N=0 e reservado a Organization."
  type        = string

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0)) && startswith(var.vpc_cidr, "10.") && can(tonumber(split(".", var.vpc_cidr)[1])) && tonumber(split(".", var.vpc_cidr)[1]) >= 0 && tonumber(split(".", var.vpc_cidr)[1]) <= 15
    error_message = "o CIDR deve ser um /16 dentro do supernet 10.0.0.0/12 (10.0 a 10.15), recebido ${var.vpc_cidr}."
  }
}

variable "availability_zones" {
  description = "AZs da regiao. Duas: o Client VPN associa uma target network por AZ."
  type        = list(string)
}

variable "supernet" {
  description = <<-EOT
    A malha inteira, uma rota so. Rota e TOPOLOGIA — o que existe e e alcancavel; nao cresce com
    celula. O que cresce com celula e authorization rule, que e POLITICA.

    Decisao irreversivel documentada em aws/docs/network/01-cidr-addressing.md.
  EOT
  type        = string
  default     = "10.0.0.0/12"
}

variable "base_domain" {
  description = "Dominio raiz sob o qual a camada dns/ delegou a subzona. Sem default: identidade, e o repo e publico."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$", var.base_domain))
    error_message = "base_domain deve ser um nome de dominio sem ponto final nem esquema (ex.: exemplo.com)."
  }
}

variable "subzone_label" {
  description = "Rotulo da subzona delegada. Tem de casar com o da raiz dns/."
  type        = string
  default     = "nonprod"

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", var.subzone_label))
    error_message = "subzone_label deve ser um unico rotulo DNS (sem ponto)."
  }
}

variable "client_cidr_block" {
  description = "Faixa de onde saem os IPs dos clientes do Client VPN. FORA do supernet de proposito, e imutavel depois de o endpoint existir."
  type        = string
  default     = "100.64.0.0/22"

  # As tres validacoes sao uma CADEIA, e as duas ultimas comecam com `!can(...)` de proposito.
  # O Terraform avalia todas as validacoes de uma variavel, nao para na primeira que falha: sem
  # a guarda, um valor sem prefixo faz `cidrhost` lancar erro de funcao DENTRO das outras duas.
  validation {
    condition     = can(cidrhost(var.client_cidr_block, 0))
    error_message = "client_cidr_block deve ser um CIDR valido com prefixo (ex.: 100.64.0.0/22)."
  }

  validation {
    condition     = !can(cidrhost(var.client_cidr_block, 0)) || tonumber(split("/", var.client_cidr_block)[1]) <= 22
    error_message = "client_cidr_block precisa de /22 ou maior (prefixo <= 22) — exigencia da AWS."
  }

  validation {
    # Nao pode cair dentro do supernet 10.0.0.0/12 (= 10.0.0.0 ate 10.15.255.255). O supernet
    # esta escrito aqui em vez de vir de local porque validacao de variavel nao alcanca local
    # — e o valor e decisao irreversivel documentada, nao configuracao.
    condition = !can(cidrhost(var.client_cidr_block, 0)) || !(
      tonumber(split(".", cidrhost(var.client_cidr_block, 0))[0]) == 10 &&
      tonumber(split(".", cidrhost(var.client_cidr_block, 0))[1]) <= 15
    )
    error_message = "client_cidr_block nao pode estar dentro do supernet 10.0.0.0/12 — colidiria com qualquer spoke, e a faixa nao muda depois de o endpoint existir."
  }
}

variable "operator_group_ids" {
  description = "IDs (UUID) dos grupos do Identity Center com authorization rule para o supernet. Lista vazia com manage_authorization ligado e ERRO."
  type        = list(string)

  validation {
    condition     = length(var.operator_group_ids) > 0 || !var.manage_authorization
    error_message = "com manage_authorization ligado, operator_group_ids nao pode ser vazia — endpoint sem rule aceita conexao e nega todo trafego."
  }

  validation {
    condition     = alltrue([for id in var.operator_group_ids : can(regex("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", id))])
    error_message = "operator_group_ids tem de conter IDs de grupo do Identity Center (UUID), nao nomes."
  }
}

variable "manage_authorization" {
  description = "Desliga as authorization rules. Tunel sobe e nada trafega — nao e estado de repouso."
  type        = bool
  default     = true
}

variable "saml_metadata_path" {
  description = "Caminho do metadata XML da aplicacao SAML do Identity Center, relativo a RAIZ que chama este modulo. Passo de console: a API CreateApplication so cria aplicacao OAuth 2.0."
  type        = string
}

variable "spoke_account_ids" {
  description = "Contas as quais o TGW e compartilhado via RAM, para que cada uma crie o proprio attachment."
  type        = list(string)

  validation {
    condition     = alltrue([for id in var.spoke_account_ids : can(regex("^[0-9]{12}$", id))])
    error_message = "spoke_account_ids tem de conter account ids de 12 digitos."
  }
}

variable "tags" {
  description = "Tags acrescentadas aos recursos do hub."
  type        = map(string)
  default     = {}
}

variable "waf_managed_rules_action" {
  description = <<-EOT
    Postura dos managed rule groups do WAF: `count` observa e deixa passar, `block` deixa cada
    grupo aplicar a acao nativa das suas regras.

    Nasce em `count` porque o guia prescritivo da AWS manda tunar com trafego de producao antes
    de bloquear, e este ALB ainda nao tem esse trafego. `block` e o estado-alvo — o criterio de
    promocao esta em docs/superpowers/specs/2026-09-02-waf-web-acl-hub-alb-design.md.
  EOT
  type        = string
  default     = "count"

  validation {
    condition     = contains(["count", "block"], var.waf_managed_rules_action)
    error_message = "waf_managed_rules_action tem de ser count ou block, recebido ${var.waf_managed_rules_action}."
  }
}

variable "waf_rate_limit_action" {
  description = <<-EOT
    Postura da rate-based rule, SEPARADA da dos managed rule groups de proposito: e a regra de
    falso positivo mais previsivel e a unica que mitiga DoS de camada 7, entao sera provavelmente
    a primeira a ser promovida a block. Uma variavel so forcaria promover tudo junto.
  EOT
  type        = string
  default     = "count"

  validation {
    condition     = contains(["count", "block"], var.waf_rate_limit_action)
    error_message = "waf_rate_limit_action tem de ser count ou block, recebido ${var.waf_rate_limit_action}."
  }
}

variable "waf_rate_limit" {
  description = "Requests por IP de origem na janela de 300s antes de a rate-based rule agir. O piso que a AWS aceita e 10."
  type        = number
  default     = 2000

  validation {
    condition     = var.waf_rate_limit >= 10
    error_message = "waf_rate_limit tem de ser no minimo 10 (piso da AWS), recebido ${var.waf_rate_limit}."
  }
}
