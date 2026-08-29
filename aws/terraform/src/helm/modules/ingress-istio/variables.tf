variable "chart_version" {
  description = <<-EOT
    Versão dos charts base, istiod e gateway. Uma só para os três: são o mesmo Istio partido em
    três charts, e versões diferentes entre eles é combinação que o projeto não suporta.
  EOT
  type        = string
  default     = "1.30.4"
}

variable "system_namespace" {
  description = "Namespace do plano de controle do Istio."
  type        = string
  default     = "istio-system"
}

variable "gateway_namespace" {
  description = "Namespace do ingress gateway, separado do plano de controle."
  type        = string
  default     = "istio-ingress"
}

variable "gateway_release_name" {
  description = <<-EOT
    Nome do release do gateway. Vira o nome do Service e, sem o prefixo `istio-`, o valor do
    rótulo `istio:` que o `Gateway` CR seleciona — ver o output gateway_selector.
  EOT
  type        = string
  default     = "istio-ingress"
}

variable "istiod_extra_values" {
  description = "YAML adicional mesclado ao values base do istiod."
  type        = string
  default     = ""
}

variable "gateway_extra_values" {
  description = "YAML adicional mesclado ao values base do gateway."
  type        = string
  default     = ""
}

variable "gateway_hosts" {
  description = <<-EOT
    Hosts que o `Gateway` CR aceita — normalmente o wildcard da célula
    (`*.<célula>.<subzona>`). Sem default: um Gateway sem host não casa requisição nenhuma, e o
    sintoma seria 404 do Envoy em tudo, indistinguível de rota faltando.
  EOT
  type        = list(string)

  validation {
    condition     = length(var.gateway_hosts) > 0
    error_message = "gateway_hosts precisa de pelo menos um host."
  }
}

variable "gateway_cr_name" {
  description = "Nome do `Gateway` CR. É por ele que os VirtualServices se referem à porta de entrada."
  type        = string
  default     = "inbound"
}
