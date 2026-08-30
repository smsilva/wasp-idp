# Cobertura migrada de network-foundation/us-east-1/tests/hub.tftest.hcl (fase 1, raiz antiga):
# o ADR 0014 orçou a migração dos 7 arquivos de connectivity/+control-plane para src/hub e
# src/cell, mas esqueceu que network-foundation também tinha teste. Sem isto, nada garante que
# o CIDR do hub fica dentro do supernet nem que o submódulo network entrega o contrato de
# subnets que o resto do hub (ALB, EKS) espera.

mock_provider "aws" {}

variables {
  name               = "poc-hub"
  region             = "us-east-1"
  vpc_cidr           = "10.1.0.0/16"
  availability_zones = ["us-east-1a", "us-east-1b"]
  base_domain        = "exemplo.com"
  operator_group_ids = ["11111111-2222-3333-4444-555555555555"]
  saml_metadata_path = "tests/fixtures/saml-metadata.xml"
  spoke_account_ids  = ["222222222222"]
}

run "cidr_dentro_do_supernet" {
  command = plan

  assert {
    condition     = can(regex("^10\\.([0-9]|1[0-5])\\.", module.network.vpc_cidr))
    error_message = "CIDR fora do supernet 10.0.0.0/12: ${module.network.vpc_cidr}"
  }

  assert {
    condition     = module.network.vpc_cidr == "10.1.0.0/16"
    error_message = "esperado 10.1.0.0/16, veio ${module.network.vpc_cidr}"
  }
}

run "contrato_de_subnets" {
  command = plan

  assert {
    condition     = length(module.network.control_plane_subnet_ids) == 4
    error_message = "o contrato de control plane são as 4 subnets"
  }

  assert {
    condition     = length(module.network.private_subnet_ids) == 2
    error_message = "deveria haver 2 subnets privadas"
  }
}
