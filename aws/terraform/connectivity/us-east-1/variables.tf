# O que é inline no main.tf e o que é variável, aqui:
#
# Inline — região, nome do hub, CIDR do supernet: decisões de desenho documentadas em
# ../../../docs/network/, não segredo (mesmo critério de network-foundation/).
#
# Variável — domínio, id do grupo do Identity Center, caminho do metadata SAML: identificam
# a conta e as pessoas de quem roda, e o repo é público. Vão por terraform.tfvars, gitignored,
# gerado por scripts/up-03-connectivity.

variable "base_domain" {
  description = <<-EOT
    Zona pai. O certificado do endpoint é emitido para
    "vpn.<subzone_label>.<base_domain>", validado por DNS na subzona que a raiz `dns/`
    delegou ao Route 53 — por isso esta raiz precisa saber o domínio.
  EOT
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$", var.base_domain))
    error_message = "base_domain deve ser um nome de domínio sem ponto final nem esquema (ex.: exemplo.com)."
  }
}

variable "subzone_label" {
  description = "Rótulo da subzona delegada. Tem de casar com o da raiz `dns/`."
  type        = string
  default     = "nonprod"

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", var.subzone_label))
    error_message = "subzone_label deve ser um único rótulo DNS (sem ponto)."
  }
}

variable "aws_profile" {
  description = "Profile local com acesso à conta network, dona do TGW e do endpoint."
  type        = string
  default     = "network"
}

variable "saml_metadata_path" {
  description = <<-EOT
    Caminho do metadata XML da aplicação SAML do Identity Center.

    NÃO é gerado por Terraform, e não é por falta de vontade: a API `CreateApplication` do
    Identity Center só cria aplicações OAuth 2.0 customizadas — aplicação SAML é passo de
    console. O arquivo é baixado de lá e fica gitignored.

    O `up-03-connectivity` para com instrução se o arquivo não existir, em vez de deixar o
    apply falhar num provider com mensagem que não explica o que falta.
  EOT
  type        = string
  default     = "saml-metadata.xml"
}

variable "operator_group_ids" {
  description = <<-EOT
    IDs dos grupos do Identity Center que recebem authorization rule para o supernet.

    IDs, não nomes: o Client VPN casa a rule contra o que vem no atributo `memberOf` da
    assertion, e o Identity Center manda IDs. Nome ali produz túnel que sobe e não alcança
    nada, com erro pouco informativo.

    Lista vazia é ERRO, não "sem regra": um endpoint sem authorization rule aceita a conexão
    e nega todo tráfego — o sintoma aparece longe da causa. Quem quiser um endpoint inútil
    de propósito passa `manage_authorization = false`.
  EOT
  type        = list(string)

  validation {
    condition     = length(var.operator_group_ids) > 0 || !var.manage_authorization
    error_message = "com manage_authorization ligado, operator_group_ids não pode ser vazia — endpoint sem rule aceita conexão e nega todo tráfego."
  }

  validation {
    # O id de grupo do Identity Center é um UUID. Nome de grupo ("platform-admins") passaria
    # por qualquer validação frouxa e falharia só no túnel.
    condition     = alltrue([for id in var.operator_group_ids : can(regex("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", id))])
    error_message = "operator_group_ids tem de conter IDs de grupo do Identity Center (UUID), não nomes."
  }
}

variable "manage_authorization" {
  description = <<-EOT
    Desliga as authorization rules. Existe para exercitar o endpoint sem grupo criado ainda
    — o grupo `cliente-a` do `4.1`, por exemplo, só nasce depois.

    Desligado, o túnel sobe e nada trafega. Não é estado de repouso.
  EOT
  type        = bool
  default     = true
}

variable "client_cidr_block" {
  description = <<-EOT
    Faixa de onde saem os IPs dos clientes conectados. FORA do supernet 10.0.0.0/12 de
    propósito: sobrepor a supernet colidiria com qualquer spoke presente ou futura, e a
    faixa não pode ser trocada depois de o endpoint existir.

    100.64.0.0/10 é o espaço de CGNAT (RFC 6598), que não é usado por VPC nenhuma daqui.
  EOT
  type        = string
  default     = "100.64.0.0/22"

  # As três validações são uma CADEIA, e as duas últimas começam com `!can(...)` de propósito.
  # O Terraform avalia todas as validações de uma variável, não para na primeira que falha: sem
  # a guarda, um valor sem prefixo faz `cidrhost` lançar erro de função DENTRO das outras duas,
  # e o que se lê é "Call to function cidrhost failed" em vez da mensagem que explica o que
  # está errado. Guardadas, elas passam de lado e a primeira reporta a causa.
  validation {
    condition     = can(cidrhost(var.client_cidr_block, 0))
    error_message = "client_cidr_block deve ser um CIDR válido com prefixo (ex.: 100.64.0.0/22)."
  }

  validation {
    # A AWS recusa /23 ou menor, e a mensagem dela chega no Create, depois de já ter criado
    # TGW e certificado. Aqui o erro é no plan.
    condition     = !can(cidrhost(var.client_cidr_block, 0)) || tonumber(split("/", var.client_cidr_block)[1]) <= 22
    error_message = "client_cidr_block precisa de /22 ou maior (prefixo <= 22) — exigência da AWS."
  }

  validation {
    # Não pode cair dentro do supernet 10.0.0.0/12 (= 10.0.0.0 até 10.15.255.255). O supernet
    # está escrito aqui em vez de vir de local porque validação de variável não alcança local
    # — e o valor é decisão irreversível documentada, não configuração.
    #
    # Não há função de containment de CIDR no Terraform; a comparação de octeto é o caminho.
    condition = !can(cidrhost(var.client_cidr_block, 0)) || !(
      tonumber(split(".", cidrhost(var.client_cidr_block, 0))[0]) == 10 &&
      tonumber(split(".", cidrhost(var.client_cidr_block, 0))[1]) <= 15
    )
    error_message = "client_cidr_block não pode estar dentro do supernet 10.0.0.0/12 — colidiria com qualquer spoke, e a faixa não muda depois de o endpoint existir."
  }
}
