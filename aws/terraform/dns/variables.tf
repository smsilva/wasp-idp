# As outras raízes trazem os valores inline, porque região, CIDR e AZs são decisões de
# desenho documentadas — não segredo. Aqui é diferente: domínio, resource group e
# subscription identificam a conta pessoal de quem roda, e o repo é público. Vão por
# terraform.tfvars, que é gitignored.

variable "base_domain" {
  description = <<-EOT
    Zona pai, a que já existe no Azure DNS. A subzona criada aqui é
    "${"nonprod"}.<base_domain>" — o apex NÃO migra para a AWS.
  EOT
  type        = string

  validation {
    # Sem ponto final e sem esquema: o nome vira parte do FQDN da subzona e do SAN do
    # certificado wildcard mais adiante.
    condition     = can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$", var.base_domain))
    error_message = "base_domain deve ser um nome de domínio sem ponto final nem esquema (ex.: exemplo.com)."
  }
}

variable "subzone_label" {
  description = <<-EOT
    Rótulo da subzona delegada. "nonprod" foi escolhido sobre "sandbox" porque Sandbox já
    tem sentido fixado no vocabulário do repo — conta de brincar, desconectada da rede — e o
    ambiente de teste do projeto é <projeto>-nonprod. "prod" segue o mesmo desenho e entra
    como outra instância desta raiz, não como exceção aqui.
  EOT
  type        = string
  default     = "nonprod"

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", var.subzone_label))
    error_message = "subzone_label deve ser um único rótulo DNS (sem ponto)."
  }
}

variable "network_profile" {
  description = "Profile local com acesso à conta network, dona da hosted zone."
  type        = string
  default     = "network"
}

variable "manage_delegation" {
  description = <<-EOT
    Liga o registro NS no Azure. Desligado, esta raiz não toca o Azure e o `plan` roda sem
    credencial de lá — necessário porque numa raiz com dois providers a ausência de
    credencial do segundo faz o plan falhar mesmo para mudança que só toca o primeiro.

    Desligar deixa a subzona SEM delegação: ela existe no Route 53 e ninguém a resolve.
    Só serve para trabalhar na parte AWS; não é estado de repouso.
  EOT
  type        = bool
  default     = true
}

variable "azure_subscription_id" {
  description = "Subscription da zona pai. Obrigatória no provider azurerm a partir do major 4."
  type        = string
  default     = null

  validation {
    condition     = !var.manage_delegation || var.azure_subscription_id != null
    error_message = "com manage_delegation ligado, azure_subscription_id é obrigatória."
  }
}

variable "azure_dns_resource_group" {
  description = "Resource group onde vive a zona pai no Azure DNS."
  type        = string
  default     = null

  validation {
    condition     = !var.manage_delegation || var.azure_dns_resource_group != null
    error_message = "com manage_delegation ligado, azure_dns_resource_group é obrigatório."
  }
}
