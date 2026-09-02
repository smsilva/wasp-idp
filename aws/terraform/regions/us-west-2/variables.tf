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

variable "network_account_id" {
  description = "Conta que hospeda a VPC hub. Declarada em variables/values.tfvars."
  type        = string
}

variable "target_account_ids" {
  description = "Contas onde o Crossplane cria recursos, via assume role. Declaradas em variables/values.tfvars."
  type        = list(string)
}

variable "endpoint_public_access" {
  description = <<-EOT
    Expor o endpoint da API do EKS na internet, restrito a public_access_cidrs. DEFAULT false —
    repassado direto a module.cell, que documenta o resto (src/cell/variables.tf).
  EOT
  type        = bool
  default     = false
}

variable "public_access_cidrs" {
  description = "CIDRs autorizados quando endpoint_public_access = true. Ver src/cell/variables.tf."
  type        = list(string)
  default     = []
}

variable "admin_principal_arns" {
  description = <<-EOT
    ARNs IAM com acesso admin ao cluster (AmazonEKSClusterAdminPolicy, escopo cluster).
    Cada ARN vira uma access entry + policy association, alem do criador do cluster.

    DEFAULT vazio: nenhum principal alem do criador tem acesso.
  EOT
  type        = list(string)
  default     = []
}

variable "admin_group_ids" {
  description = <<-EOT
    Grupos do Identity Center com acesso admin ao cluster. Chave = NOME do permission set
    (ex.: "PlatformAdmin"), valor = GroupId (UUID) do grupo atribuido a ele.

    O GroupId nao entra em nenhuma chamada AWS: o vinculo grupo -> role provisionada existe
    so no Identity Center, e o nome da role (AWSReservedSSO_<PermissionSet>_<hash>) carrega
    apenas o permission set. O UUID fica aqui para rastreabilidade de QUAL grupo recebeu o
    acesso, e e validado como UUID para nao aceitar nome de grupo por engano.

    Exige bootstrap manual previo (permission set + account assignment na conta cicd):
    ver aws/docs/bootstrap/.

    DEFAULT vazio: nenhum grupo tem acesso.
  EOT
  type        = map(string)
  default     = {}

  validation {
    condition     = alltrue([for id in values(var.admin_group_ids) : can(regex("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", id))])
    error_message = "admin_group_ids tem de mapear nome do permission set -> GroupId do Identity Center (UUID), nao nome de grupo."
  }
}
