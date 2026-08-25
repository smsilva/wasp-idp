mock_provider "aws" {}

variables {
  region             = "us-east-1"
  aws_profile        = "network"
  prefix             = "poc"
  hub_vpc_cidr       = "10.1.0.0/16"
  availability_zones = ["us-east-1a", "us-east-1b"]
  state_bucket_name  = "test-tfstate-bucket"
}

run "o_contrato_de_subnets_do_hub" {
  command = plan

  # Assertion de teste em raiz só alcança outputs de módulo, não os recursos internos
  # dele — a ausência de NAT é coberta em src/network/tests/routing.tftest.hcl.
  assert {
    condition     = length(module.hub_network.private_subnet_ids) == 2
    error_message = "o hub deveria ter 2 subnets privadas"
  }

  assert {
    condition     = length(module.hub_network.control_plane_subnet_ids) == 4
    error_message = "o contrato de control plane são as 4 subnets"
  }
}

run "o_cidr_do_hub_e_o_slash16_n1_do_supernet" {
  command = plan

  assert {
    condition     = module.hub_network.vpc_cidr == "10.1.0.0/16"
    error_message = "o hub deveria usar 10.1.0.0/16 (N=1); N=0 é reservado para a Organization"
  }
}

run "recusa_cidr_fora_do_supernet" {
  command = plan

  variables {
    hub_vpc_cidr = "192.168.0.0/16"
  }

  # O plano de CIDR é 10.0.0.0/12 e é a única decisão irreversível da cadeia.
  expect_failures = [var.hub_vpc_cidr]
}

run "recusa_cidr_acima_do_teto_do_supernet" {
  command = plan

  variables {
    # 10.16.x está FORA do /12, que termina em 10.15.255.255. É o off-by-one que um
    # startswith("10.") deixaria passar.
    hub_vpc_cidr = "10.16.0.0/16"
  }

  expect_failures = [var.hub_vpc_cidr]
}
