# A raiz expoe o hub como output. A celula (fase 3) le o hub SO por aqui, nunca por data source —
# cada output e um data source que morre do outro lado. Os nomes casam com os do src/hub, que por
# sua vez casam com o que a connectivity/ lia por tag.

output "vpc_id" {
  description = "VPC hub. Origem do security group do cluster da celula."
  value       = module.hub.vpc_id
}

output "vpc_cidr_block" {
  description = "CIDR da VPC hub. O Client VPN faz SNAT, entao o trafego chega a celula com origem AQUI."
  value       = module.hub.vpc_cidr_block
}

output "private_subnet_ids" {
  description = "Subnets privadas do hub. Target networks do Client VPN."
  value       = module.hub.private_subnet_ids
}

output "public_subnet_ids" {
  description = "Subnets publicas do hub. Onde o ALB de ingress vive."
  value       = module.hub.public_subnet_ids
}

output "transit_gateway_id" {
  description = "TGW ao qual a celula anexa a propria VPC."
  value       = module.hub.transit_gateway_id
}

output "transit_gateway_route_table_id" {
  description = "Route table do HUB. A da celula nasce no proprio modulo da celula."
  value       = module.hub.transit_gateway_route_table_id
}

output "transit_gateway_attachment_id" {
  description = "Attachment da propria VPC hub — o que a celula propaga para a route table dela."
  value       = module.hub.transit_gateway_attachment_id
}

output "alb_arn" {
  description = "ALB publico do hub. A celula anexa listener rule por host."
  value       = module.hub.alb_arn
}

output "alb_listener_arn" {
  description = "Listener :443 compartilhado. A celula anexa o proprio certificado por SNI."
  value       = module.hub.alb_listener_arn
}

output "alb_dns_name" {
  description = "Alvo dos registros A alias das celulas."
  value       = module.hub.alb_dns_name
}

output "alb_zone_id" {
  description = "Zone id canonica do ALB, par obrigatorio do dns_name num registro alias."
  value       = module.hub.alb_zone_id
}

output "alb_security_group_id" {
  description = "SG do ALB. A celula autoriza a origem do health check."
  value       = module.hub.alb_security_group_id
}

output "client_vpn_endpoint_id" {
  description = "Endpoint do Client VPN. Usado para exportar o .ovpn."
  value       = module.hub.client_vpn_endpoint_id
}

output "client_vpn_dns_name" {
  description = "Hostname que o client usa. MUDA a cada recriacao."
  value       = module.hub.client_vpn_dns_name
}

output "authorized_group_ids" {
  description = "Grupos com authorization rule no Client VPN."
  value       = module.hub.authorized_group_ids
}
