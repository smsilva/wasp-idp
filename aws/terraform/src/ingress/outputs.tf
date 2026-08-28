output "target_group_arn" {
  description = <<-EOT
    O que o cluster precisa saber. Nao e o NLB: e o ARN da target group, que e o que o
    TargetGroupBinding do LBC consome para registrar os pods do gateway. Vai para o ConfigMap
    platform-bootstrap como ingressTargetGroupArn.
  EOT
  value       = aws_lb_target_group.gateway.arn
}

output "private_ips" {
  description = <<-EOT
    Os enderecos fixos do NLB, um por AZ. E o que a target group do lado HUB registra (fase
    3.2). Conhecidos em tempo de plan porque sao calculados, nao lidos do recurso — dai a
    fase 3.2 poder ser escrita sem esperar o NLB existir.
  EOT
  value       = local.private_ips
}

output "security_group_id" {
  description = <<-EOT
    SG do NLB. O TargetGroupBinding referencia este id em networking.ingress, em vez de um
    CIDR solto: assim a regra que o LBC cria no SG dos pods nomeia a origem exata.
  EOT
  value       = aws_security_group.nlb.id
}

output "dns_name" {
  description = "Nome do NLB. Util para diagnostico; o hub nao o usa, aponta para os IPs fixos."
  value       = aws_lb.ingress.dns_name
}
