output "subzone_name" {
  description = "FQDN da subzona. Base dos nomes de cluster (<id>.<subzona>) e do wildcard de ACM."
  value       = aws_route53_zone.subzone.name
}

output "subzone_id" {
  description = <<-EOT
    Hosted zone id da subzona. É o escopo da policy do external-dns e do cert-manager: eles
    recebem esta zona e nenhuma outra.
  EOT
  value       = aws_route53_zone.subzone.zone_id
}

output "subzone_name_servers" {
  description = "Name servers atribuídos pela AWS. Já cabeados no registro NS da pai quando manage_delegation está ligado."
  value       = aws_route53_zone.subzone.name_servers
}

output "delegation_managed" {
  description = "Falso significa subzona sem delegação: existe no Route 53 e ninguém resolve."
  value       = var.manage_delegation
}
