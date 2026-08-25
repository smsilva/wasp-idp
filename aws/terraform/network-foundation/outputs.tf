output "hub_vpc_id" {
  value = module.hub_network.vpc_id
}

output "hub_vpc_cidr" {
  value = module.hub_network.vpc_cidr
}

output "hub_private_subnet_ids" {
  value = module.hub_network.private_subnet_ids
}

output "hub_control_plane_subnet_ids" {
  value = module.hub_network.control_plane_subnet_ids
}

output "state_bucket_name" {
  description = "Bucket que hospeda o state a partir da migração da Task 5."
  value       = module.state_backend.bucket_name
}
