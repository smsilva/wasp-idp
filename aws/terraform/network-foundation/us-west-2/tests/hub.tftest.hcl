mock_provider "aws" {}

run "cidr_dentro_do_supernet" {
  command = plan

  # A validação de supernet vivia na variável hub_vpc_cidr da raiz antiga. Com os valores
  # inline ela precisa viver aqui, senão um typo no CIDR passa direto — e CIDR é a única
  # decisão irreversível da cadeia. 10.0.0.0/12 cobre 10.0.x a 10.15.x.
  assert {
    condition     = can(regex("^10\\.([0-9]|1[0-5])\\.", module.hub_network.vpc_cidr))
    error_message = "CIDR fora do supernet 10.0.0.0/12: ${module.hub_network.vpc_cidr}"
  }

  assert {
    condition     = module.hub_network.vpc_cidr == "10.3.0.0/16"
    error_message = "esperado 10.3.0.0/16, veio ${module.hub_network.vpc_cidr}"
  }
}

run "contrato_de_subnets" {
  command = plan

  assert {
    condition     = length(module.hub_network.control_plane_subnet_ids) == 4
    error_message = "o contrato de control plane são as 4 subnets"
  }

  assert {
    condition     = length(module.hub_network.private_subnet_ids) == 2
    error_message = "deveria haver 2 subnets privadas"
  }
}

# As públicas saem da raiz porque o ALB do hub (passo 3.2) as consome de outra camada. O
# alternativo — data "aws_subnets" filtrando por tag:Name = poc-hub-public-* — quebra em
# silêncio se o nome mudar; o output falha alto.
#
# Os dois runs abaixo existem porque UM override prova o valor, não a ligação: com uma lista
# só, um valor colado à mão no outputs.tf igual ao injetado passaria verde. Tamanhos
# diferentes (2 e 3) e valores diferentes não são satisfazíveis por nenhuma lista fixa. E o
# override é necessário porque id de subnet é computado: comparar dois desconhecidos daria
# "Unknown condition value" em vez de comparar.
run "publicas_saem_da_raiz" {
  command = plan

  override_module {
    target = module.hub_network
    outputs = {
      public_subnet_ids  = ["subnet-pub-1a", "subnet-pub-1b"]
      private_subnet_ids = ["subnet-priv-1a", "subnet-priv-1b"]
    }
  }

  assert {
    condition     = toset(output.hub_public_subnet_ids) == toset(["subnet-pub-1a", "subnet-pub-1b"])
    error_message = "hub_public_subnet_ids não veio de public_subnet_ids: ${jsonencode(output.hub_public_subnet_ids)}"
  }

  # Pega a troca mais provável: as privadas também são duas, então nenhuma asserção de
  # tamanho distinguiria uma da outra.
  assert {
    condition     = length(setintersection(toset(output.hub_public_subnet_ids), toset(["subnet-priv-1a", "subnet-priv-1b"]))) == 0
    error_message = "hub_public_subnet_ids contém subnet privada"
  }
}

run "publicas_saem_da_raiz_com_outro_tamanho" {
  command = plan

  override_module {
    target = module.hub_network
    outputs = {
      public_subnet_ids  = ["subnet-pub-2a", "subnet-pub-2b", "subnet-pub-2c"]
      private_subnet_ids = ["subnet-priv-2a", "subnet-priv-2b"]
    }
  }

  assert {
    condition     = toset(output.hub_public_subnet_ids) == toset(["subnet-pub-2a", "subnet-pub-2b", "subnet-pub-2c"])
    error_message = "hub_public_subnet_ids não acompanhou o segundo override: ${jsonencode(output.hub_public_subnet_ids)}"
  }
}
