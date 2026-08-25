variable "region" {
  description = "Única região aprovada pela SCP DenyOutsideApprovedRegions."
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = <<-EOT
    Profile local que assume OrganizationAccountAccessRole na conta network.
    Depende de `aws sso login --profile personal` ativo.
  EOT
  type        = string
  default     = "network"
}

variable "prefix" {
  description = "Prefixo de naming: <prefix>-hub-vpc, <prefix>-hub-igw, ..."
  type        = string
}

variable "hub_vpc_cidr" {
  description = <<-EOT
    CIDR da VPC hub. Um /16 do supernet 10.0.0.0/12; N=0 é reservado para a
    Organization, então o hub é N=1. Ver aws/docs/network/01-cidr-addressing.md.
  EOT
  type        = string

  validation {
    # Terraform não tem builtin de "está contido em". O supernet 10.0.0.0/12 cobre
    # 10.0.0.0–10.15.255.255, então basta checar o 1º e o 2º octeto.
    condition = (
      can(cidrhost(var.hub_vpc_cidr, 0)) &&
      can(regex("^10\\.([0-9]|1[0-5])\\.", var.hub_vpc_cidr))
    )
    error_message = "hub_vpc_cidr deve pertencer ao supernet 10.0.0.0/12 (10.0.x a 10.15.x)."
  }
}

variable "availability_zones" {
  description = "Exatamente 2 AZs da região."
  type        = list(string)
}

variable "state_bucket_name" {
  description = "Nome do bucket de state. Valor real em terraform.tfvars (gitignored)."
  type        = string
}
