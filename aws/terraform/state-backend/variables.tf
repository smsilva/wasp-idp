variable "region" {
  description = "Região do bucket de state. Global no sentido de uso — todas as regiões gravam nele."
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "Profile local que assume OrganizationAccountAccessRole na conta network."
  type        = string
  default     = "network"
}

variable "bucket_name" {
  description = "Nome do bucket. Valor real em terraform.tfvars (gitignored)."
  type        = string
}
