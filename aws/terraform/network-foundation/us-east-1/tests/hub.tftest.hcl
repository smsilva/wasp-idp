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
    condition     = module.hub_network.vpc_cidr == "10.1.0.0/16"
    error_message = "esperado 10.1.0.0/16, veio ${module.hub_network.vpc_cidr}"
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
