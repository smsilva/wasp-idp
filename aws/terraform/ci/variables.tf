variable "region" {
  description = "Regiao onde os providers desta raiz operam. IAM e OIDC provider sao globais, mas o provider AWS exige um valor."
  type        = string
  default     = "us-east-1"
}

variable "cicd_profile" {
  description = "Profile local com acesso a conta cicd. Quem aplica esta raiz — um admin humano, uma vez."
  type        = string
  default     = "cicd"
}

variable "network_profile" {
  description = "Profile local com acesso a conta network."
  type        = string
  default     = "network"
}

variable "github_org" {
  description = "Organizacao/usuario do GitHub dono do repositorio que dispara o workflow."
  type        = string
  default     = "smsilva"
}

variable "github_repo" {
  description = "Nome do repositorio no GitHub."
  type        = string
  default     = "wasp-idp"
}

variable "role_name" {
  description = "Nome das duas roles (uma por conta) assumidas pelo workflow do GitHub Actions."
  type        = string
  default     = "github-actions-provision"
}
