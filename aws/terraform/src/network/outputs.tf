output "vpc_id" {
  description = "Equivalente a Network.status.vpcId na Composition de referência."
  value       = aws_vpc.this.id
}

output "vpc_cidr" {
  value = aws_vpc.this.cidr_block
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "As privadas — destino dos node groups."
  value       = aws_subnet.private[*].id
}

output "control_plane_subnet_ids" {
  description = <<-EOT
    As 4 subnets (públicas + privadas). Equivalente a
    Network.status.subnetIds.controlPlane; é o que o EKS consome.
  EOT
  value       = concat(aws_subnet.public[*].id, aws_subnet.private[*].id)
}

output "private_subnet_cidrs" {
  description = <<-EOT
    Os CIDRs das privadas, na MESMA ordem de private_subnet_ids. Existe para quem precisa
    fixar um endereço dentro da subnet — o NLB interno do ingress usa
    subnet_mapping { private_ipv4_address = cidrhost(<este cidr>, N) }, porque ler IP privado
    de NLB depois do apply é frágil (aws_lb não os expõe; o caminho usual é caçar ENI por
    descrição). Fixando, o endereço é conhecido em tempo de plan e estável entre recriações.
  EOT
  value       = aws_subnet.private[*].cidr_block
}

output "private_route_table_id" {
  description = "Única, compartilhada por todas as subnets privadas — quem anexa TGW referencia esta."
  value       = aws_route_table.private.id
}
