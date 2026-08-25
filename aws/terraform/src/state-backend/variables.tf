variable "bucket_name" {
  description = <<-EOT
    Nome do bucket de state. Globalmente único na AWS — incluir um discriminador de
    Organization ou conta. Valor real fica em terraform.tfvars (gitignored).
  EOT
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.bucket_name))
    error_message = "bucket_name deve seguir as regras de nome de bucket S3 (minúsculas, 3-63 chars)."
  }
}

variable "tags" {
  description = "Tags adicionais."
  type        = map(string)
  default     = {}
}
