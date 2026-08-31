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

variable "github_owner_id" {
  description = <<-EOT
    ID numerico imutavel do dono do repositorio no GitHub (gh api users/<owner> --jq .id).
    Necessario porque o dono ou o repositorio ja foi renomeado: apos um rename, o claim `sub`
    do token OIDC do GitHub Actions passa a incluir os IDs (repo:<owner>@<owner_id>/<repo>@<repo_id>:...)
    em vez do formato simples repo:<owner>/<repo>:... — confirmado via CloudTrail num
    AssumeRoleWithWebIdentity real que falhou contra o trust simples. Ver ci/README.md.
  EOT
  type        = string
  default     = "287870"
}

variable "github_repo_id" {
  description = "ID numerico imutavel do repositorio no GitHub (gh api repos/<owner>/<repo> --jq .id). Ver github_owner_id."
  type        = string
  default     = "522972834"
}

variable "role_name" {
  description = "Nome das duas roles (uma por conta) assumidas pelo workflow do GitHub Actions."
  type        = string
  default     = "github-actions-provision"
}
