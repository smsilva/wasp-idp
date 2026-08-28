output "hub_vpc_id" {
  value = module.hub_network.vpc_id
}

output "hub_vpc_cidr" {
  value = module.hub_network.vpc_cidr
}

output "hub_private_subnet_ids" {
  value = module.hub_network.private_subnet_ids
}

output "hub_public_subnet_ids" {
  description = <<-EOT
    Destino do ALB do hub (passo 3.2), que vive na camada connectivity/ e precisa das
    públicas de outra camada. Sai como output em vez de data "aws_subnets" por tag:Name
    porque um filtro por padrão de nome quebra em silêncio se o nome mudar.
  EOT
  value       = module.hub_network.public_subnet_ids
}

output "hub_control_plane_subnet_ids" {
  value = module.hub_network.control_plane_subnet_ids
}
