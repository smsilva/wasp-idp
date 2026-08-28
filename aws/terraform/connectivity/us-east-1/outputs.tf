output "transit_gateway_id" {
  description = <<-EOT
    O que a camada 4 consome para criar o attachment da spoke. Lido por data source do
    outro lado (por tag), não por terraform_remote_state — mas o output existe para o
    script `vpn`/`status` e para conferência humana.
  EOT
  value       = aws_ec2_transit_gateway.hub.id
}

output "transit_gateway_route_table_id" {
  description = "Route table do hub. As de tenant nascem no state do spoke."
  value       = aws_ec2_transit_gateway_route_table.hub.id
}

output "transit_gateway_attachment_id" {
  description = <<-EOT
    O attachment da própria VPC hub — pertence a este state. O script `destroy` o exclui da
    checagem de "attachment de fora", senão o attachment do hub sozinho já faria a checagem
    recusar um destroy legítimo desta camada.
  EOT
  value       = aws_ec2_transit_gateway_vpc_attachment.hub.id
}

output "client_vpn_endpoint_id" {
  value = aws_ec2_client_vpn_endpoint.hub.id
}

output "client_vpn_dns_name" {
  description = <<-EOT
    Hostname que o client usa. MUDA a cada recriação do endpoint — é a razão de o script
    `vpn config` exportar a configuração corrente a cada uso em vez de cachear um .ovpn.
  EOT
  value       = aws_ec2_client_vpn_endpoint.hub.dns_name
}

output "server_certificate_domain" {
  description = "Nome do certificado do endpoint. Não casa com o hostname de conexão de propósito — o client confere extended key usage, não nome."
  value       = aws_acm_certificate.vpn.domain_name
}

output "alb_arn" {
  description = <<-EOT
    O ALB público do hub. Como o TGW acima, a camada 4 o descobre por data source (por nome)
    e não por terraform_remote_state; o output existe para script e conferência humana.
  EOT
  value       = aws_lb.hub.arn
}

output "alb_listener_arn" {
  description = "Listener :443 compartilhado. Cada célula anexa o próprio certificado por SNI e a própria rule."
  value       = aws_lb_listener.https.arn
}

output "alb_dns_name" {
  description = <<-EOT
    Alvo dos registros A alias das células. MUDA a cada recriação do ALB — e o ALB é recriado
    com esta camada. Não cachear: a ordem de subida (03 antes de 04) e de descida (04 antes de
    03) é o que garante que nenhum alias aponte para um ALB morto.
  EOT
  value       = aws_lb.hub.dns_name
}

output "alb_zone_id" {
  description = "Zone id canônica do ALB, par obrigatório do dns_name num registro alias."
  value       = aws_lb.hub.zone_id
}

output "alb_security_group_id" {
  description = "SG do ALB. Origem que a spoke libera no SG do próprio NLB seria este, se o caminho não fosse por CIDR — hoje a spoke libera o CIDR da VPC hub."
  value       = aws_security_group.alb.id
}

output "alb_default_certificate_domain" {
  description = "Certificado default do listener, wildcard de um nível da subzona. Não serve tráfego de célula — os certificados por célula entram por SNI."
  value       = aws_acm_certificate.alb.domain_name
}

output "aws_profile" {
  description = "Profile que aplicou esta camada. O script `destroy` o consome para consultar attachments com a credencial certa em vez de adivinhar."
  value       = var.aws_profile
}

output "authorized_group_ids" {
  description = "Grupos com authorization rule. Vazio significa túnel que sobe e não trafega."
  value       = [for rule in aws_ec2_client_vpn_authorization_rule.operators : rule.access_group_id]
}
