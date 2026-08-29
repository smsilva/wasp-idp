variable "name" {
  description = "Nome do release e do CR TargetGroupBinding."
  type        = string
  default     = "istio-ingress"
}

variable "namespace" {
  description = <<-EOT
    Namespace do CR. Tem de ser o MESMO do Service referenciado — `serviceRef` não atravessa
    namespace. Vem do output gateway_namespace do módulo ingress-istio.
  EOT
  type        = string
}

variable "target_group_arn" {
  description = <<-EOT
    ARN da target group do NLB interno. Sem default de propósito: o ARN muda a cada recriação
    da target group (`name_prefix` + create_before_destroy), então tem de chegar por referência
    de Terraform. Um valor colado à mão fica velho no primeiro replace, e o sintoma é uma target
    group vazia com tudo aparentemente saudável.
  EOT
  type        = string
}

variable "vpc_id" {
  description = "VPC da célula. O controller a usa para resolver os IPs dos pods."
  type        = string
}

variable "service_name" {
  description = "Nome do Service do ingress gateway. Vem do output gateway_service_name do ingress-istio."
  type        = string
}

variable "service_port" {
  description = <<-EOT
    Porta do Service do gateway. 80, não 8080: o chart do gateway mapeia Service 80 →
    targetPort 80, e é a 80 que a target group declara e que o security group libera. 8080 é do
    Istio antigo, e o sintoma de errar aqui é "nenhum target saudável" sem nada errado no
    cluster.
  EOT
  type        = number
  default     = 80
}

variable "target_type" {
  description = "Tipo de target. `ip` para casar com a target group de src/ingress — registra pods, não nós."
  type        = string
  default     = "ip"

  validation {
    condition     = contains(["ip", "instance"], var.target_type)
    error_message = "target_type só aceita ip ou instance, recebido ${var.target_type}."
  }
}
