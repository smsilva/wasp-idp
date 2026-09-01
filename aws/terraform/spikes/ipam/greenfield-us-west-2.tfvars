# Cenario GREENFIELD — o dia zero, sem VPC pre-existente no espaco do pool.
#
# us-west-2 tem ZERO recursos nossos aplicados (regions/us-west-2/ nunca foi aplicada), e o /14
# desta regiao — 10.4.0.0/14 — nao contem nenhuma VPC. E o mais proximo de "Organization nova" que
# se consegue sem criar uma Organization: no que importa para o IPAM (o espaco do pool), e greenfield
# de verdade.
#
# A VPC default de us-west-2 (172.31.0.0/16) NAO interfere: esta fora do supernet 10.0.0.0/12, logo
# fora de qualquer pool. Ela e o assunto da issue #67, nao deste teste.

region = "us-west-2"

# Uma unica regiao: o IPAM so opera onde precisa operar. Nao declarar us-east-1 aqui e o que torna o
# teste greenfield — com ela na lista, o pool de la tentaria auto-importar 10.1 e 10.2 e estariamos
# repetindo o cenario brownfield.
regional_blocks = {
  "us-west-2" = "10.4.0.0/14"
}

# Desligado: o bloco reservado a Organization (10.0.0.0/16) vive no /14 de us-east-1, que este teste
# nao cria. Tentar aloca-lo do pool de us-west-2 falharia, e por motivo certo.
organization_reserved_block = null
