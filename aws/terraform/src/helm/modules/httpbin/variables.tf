variable "name" {
  description = "Nome do release, do Deployment, do Service e do VirtualService."
  type        = string
  default     = "httpbin"
}

variable "namespace" {
  description = "Namespace do workload de prova, separado do namespace do ingress."
  type        = string
  default     = "httpbin"
}

variable "host" {
  description = <<-EOT
    Host que este workload atende. Sem default: é `services.<célula>.<subzona>`, e só a camada
    que conhece a célula sabe montá-lo. Qualquer outro host sob o wildcard cai no
    `fixed-response` 404 do listener do ALB e parece falha de ingress.
  EOT
  type        = string
}

variable "gateway_ref" {
  description = <<-EOT
    Referência do `Gateway` CR no formato `<namespace>/<nome>`, vinda do output gateway_ref do
    módulo ingress-istio. O nome curto resolveria no namespace deste VirtualService, onde o
    Gateway não está — e a rota simplesmente não existiria, sem erro nenhum.
  EOT
  type        = string

  validation {
    condition     = length(split("/", var.gateway_ref)) == 2
    error_message = "gateway_ref precisa da forma <namespace>/<nome>, recebido ${var.gateway_ref}."
  }
}

variable "image_tag" {
  description = "Tag da imagem go-httpbin."
  type        = string
  default     = "2.21.0"
}

variable "extra_values" {
  description = "YAML adicional mesclado ao values base."
  type        = string
  default     = ""
}
