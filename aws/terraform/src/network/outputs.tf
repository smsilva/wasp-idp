output "vpc_id" {
  description = "Equivalente a Network.status.vpcId na Composition de referência."
  value       = aws_vpc.this.id
}

output "vpc_cidr" {
  value = aws_vpc.this.cidr_block
}

output "availability_zones" {
  description = "AZs em que as subnets deste modulo nasceram. Existe para a raiz assertar de onde a lista veio."
  value       = var.availability_zones
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

output "public_route_table_id" {
  description = <<-EOT
    Única, compartilhada por todas as subnets públicas. Existe porque a rota até a malha não
    pode viver só na privada: o EKS distribui as ENIs do endpoint entre TODAS as subnets que
    recebe (control_plane_subnet_ids), então uma ENI numa pública responde pelo default da
    tabela dela — o IGW — e o tráfego que veio do hub pelo TGW morre assimétrico.
  EOT
  value       = aws_route_table.public.id
}
