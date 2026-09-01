output "ipam_id" {
  description = "Id do IPAM. So existe um por conta/regiao — enquanto este spike estiver de pe, o slot da conta `network` esta ocupado."
  value       = aws_vpc_ipam.this.id
}

output "private_scope_id" {
  description = "Escopo privado default. Um segundo escopo privado (o que sustenta CIDR repetido entre tenants que nao se falam) NAO e criado aqui — e gatilho futuro, nao setup."
  value       = aws_vpc_ipam.this.private_default_scope_id
}

output "regional_pool_ids" {
  description = "Pool regional por regiao. E deste id que uma raiz passaria a alocar, no lugar do CIDR literal."
  value       = { for region, pool in aws_vpc_ipam_pool.regional : region => pool.id }
}

output "proof_vpc_cidr" {
  description = "CIDR que a AWS escolheu para a VPC de prova. Nenhum CIDR foi escrito na configuracao — este valor E o resultado do spike."
  value       = aws_vpc.proof.cidr_block
}

output "proof_vpc_id" {
  value       = aws_vpc.proof.id
  description = "VPC de prova, na conta spoke, alocada do pool compartilhado por RAM."
}

# Como conferir a adocao das VPCs ja existentes (prova 3). O auto_import e assincrono: a doc registra
# atraso de ate ~20 min no monitoramento, entao lista vazia logo apos o apply NAO significa falha.
output "how_to_verify_adoption" {
  description = "Comando que lista o que o IPAM adotou — a evidencia da prova 3."
  value       = <<-EOT
    aws ec2 get-ipam-pool-allocations \
      --ipam-pool-id ${aws_vpc_ipam_pool.regional[var.region].id} \
      --profile ${var.network_profile} --region ${var.region} --output json > /tmp/ipam-alloc.json
  EOT
}
