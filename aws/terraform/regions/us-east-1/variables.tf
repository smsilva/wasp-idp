variable "base_domain" {
  description = <<-EOT
    Dominio raiz sob o qual a camada dns/ delegou a subzona.

    SEM DEFAULT de proposito: e valor por-conta num repo publico, e a ausencia faz o plan falhar
    com uma mensagem que diz o que falta — em vez de herdar o dominio de outra conta. Declarado em
    variables/values.tfvars, carregado por values.auto.tfvars.
  EOT
  type        = string

  validation {
    condition     = length(var.base_domain) > 0 && !endswith(var.base_domain, ".") && length(split(".", var.base_domain)) >= 2
    error_message = "base_domain deve ser um dominio sem ponto final, com ao menos dois labels, recebido ${var.base_domain}."
  }
}

variable "subzone_label" {
  description = "Label da subzona delegada pela camada dns/. `sandbox` NAO e ambiente de teste — o de teste e nonprod."
  type        = string
  default     = "nonprod"
}

variable "aws_profile" {
  description = "Profile local com acesso a conta cicd, dona da celula. Provider default desta raiz."
  type        = string
  default     = "cicd"
}

variable "network_profile" {
  description = "Profile local com acesso a conta network, dona da VPC hub, do TGW e do ALB."
  type        = string
  default     = "network"
}

variable "operator_group_ids" {
  description = "IDs (UUID) dos grupos do Identity Center com authorization rule no Client VPN."
  type        = list(string)
}

variable "spoke_account_ids" {
  description = "Contas as quais o TGW e compartilhado via RAM. Uma por celula."
  type        = list(string)
}

variable "saml_metadata_path" {
  description = <<-EOT
    Caminho do metadata XML da aplicacao SAML, relativo a esta raiz. Passo de console.

    O default e um symlink para ../../variables/saml-metadata.xml: UMA aplicacao do Identity
    Center serve todas as regioes, porque o ACS URL do Client VPN e http://127.0.0.1:35001 em
    qualquer endpoint. O que e por regiao e o aws_iam_saml_provider criado a partir dele, e o
    src/hub ja regionaliza esse nome.
  EOT
  type        = string
  default     = "saml-metadata.xml"
}
