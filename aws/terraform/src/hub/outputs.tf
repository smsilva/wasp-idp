output "vpc_id" {
  description = "VPC hub. Substitui data.aws_vpc.hub na celula."
  value       = module.network.vpc_id
}

output "vpc_cidr_block" {
  description = "CIDR da VPC hub. E a origem que o security group do cluster autoriza em 443 — o Client VPN faz SNAT, entao o trafego chega com origem AQUI, nao no client CIDR."
  value       = module.network.vpc_cidr
}

output "private_subnet_ids" {
  description = "Subnets privadas do hub. Target networks do Client VPN."
  value       = module.network.private_subnet_ids
}

output "public_subnet_ids" {
  description = "Subnets publicas do hub. Onde o ALB de ingress vive."
  value       = module.network.public_subnet_ids
}

output "transit_gateway_id" {
  description = "Substitui data.aws_ec2_transit_gateway.hub na celula."
  value       = aws_ec2_transit_gateway.hub.id
}

output "transit_gateway_route_table_id" {
  description = "Route table do HUB. A da celula nasce no proprio modulo da celula. Substitui data.aws_ec2_transit_gateway_route_table.hub."
  value       = aws_ec2_transit_gateway_route_table.hub.id
}

output "transit_gateway_attachment_id" {
  description = "Attachment da propria VPC hub — o que a celula propaga para a route table dela. Substitui data.aws_ec2_transit_gateway_vpc_attachment.hub."
  value       = aws_ec2_transit_gateway_vpc_attachment.hub.id
}

output "alb_arn" {
  description = "ALB publico do hub. Substitui data.aws_lb.hub_ingress."
  value       = aws_lb.hub.arn
}

output "alb_listener_arn" {
  description = "Listener :443 compartilhado. Cada celula anexa o proprio certificado por SNI e a propria rule. Substitui data.aws_lb_listener.hub_https."
  value       = aws_lb_listener.https.arn
}

output "alb_dns_name" {
  description = "Alvo dos registros A alias das celulas. MUDA a cada recriacao do ALB."
  value       = aws_lb.hub.dns_name
}

output "alb_zone_id" {
  description = "Zone id canonica do ALB, par obrigatorio do dns_name num registro alias."
  value       = aws_lb.hub.zone_id
}

output "alb_security_group_id" {
  description = "SG do ALB."
  value       = aws_security_group.alb.id
}

output "client_vpn_endpoint_id" {
  value = aws_ec2_client_vpn_endpoint.hub.id
}

output "client_vpn_dns_name" {
  description = "Hostname que o client usa. MUDA a cada recriacao — nunca cachear um .ovpn."
  value       = aws_ec2_client_vpn_endpoint.hub.dns_name
}

output "authorized_group_ids" {
  description = "Grupos com authorization rule. Vazio significa tunel que sobe e nao trafega."
  value       = [for rule in aws_ec2_client_vpn_authorization_rule.operators : rule.access_group_id]
}
