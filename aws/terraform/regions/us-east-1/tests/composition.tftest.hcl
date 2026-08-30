# O que a raiz decide, em teste: o recorte das AZs (duas, para o Client VPN e o NLB da celula) e
# a nao-sobreposicao dos CIDRs do hub e da celula. A ligacao hub->celula entra na fase 3; aqui a
# celula ainda nem existe, entao so se asserta o que ja e decidido.

mock_provider "aws" {}
mock_provider "aws" { alias = "network" }

variables {
  base_domain        = "exemplo.com"
  operator_group_ids = ["00000000-0000-0000-0000-000000000000"]
  spoke_account_ids  = ["000000000000"]
  saml_metadata_path = "../../src/hub/tests/fixtures/saml-metadata.xml"
}

# Mesma razao do override global nos testes do src/hub: aws_ram_resource_association (dentro do
# module.hub) valida resource_arn como ARN de verdade, e o valor sintetico que o mock da ao
# aws_ec2_transit_gateway.hub nao e um ARN valido. O alvo e o endereco completo a partir da raiz.
override_resource {
  target = module.hub.aws_ec2_transit_gateway.hub
  values = {
    arn = "arn:aws:ec2:us-east-1:000000000000:transit-gateway/tgw-0000000000000000f"
  }
}

# Tres AZs disponiveis, o hub fica com as DUAS primeiras — slice, nao a lista inteira. Duas porque
# o Client VPN associa uma target network por AZ e o NLB interno da celula fixa um IP por AZ.
run "hub_gets_the_first_two_availability_zones" {
  command = plan

  override_data {
    target = data.aws_availability_zones.this
    values = {
      names = ["us-east-1a", "us-east-1b", "us-east-1c"]
    }
  }

  assert {
    condition     = length(local.availability_zones) == 2
    error_message = "o hub tem de receber DUAS AZs, recebido ${length(local.availability_zones)}"
  }

  # Nao basta a contagem: as duas tem de ser as PRIMEIRAS da lista. Um slice (2, 4) passaria na
  # contagem e escolheria AZs erradas sem ninguem perceber no plan.
  assert {
    condition     = toset(local.availability_zones) == toset(["us-east-1a", "us-east-1b"])
    error_message = "as AZs tem de ser as duas primeiras da regiao, recebido ${jsonencode(local.availability_zones)}"
  }
}

run "hub_and_cell_cidrs_do_not_overlap" {
  command = plan

  override_data {
    target = data.aws_availability_zones.this
    values = {
      names = ["us-east-1a", "us-east-1b"]
    }
  }

  # Nao ha funcao de containment de CIDR no Terraform; a comparacao de octeto e o caminho, o mesmo
  # padrao ja usado na validacao do client_cidr_block do src/hub.
  assert {
    condition     = split(".", local.hub_vpc_cidr)[1] != split(".", local.cell_vpc_cidr)[1]
    error_message = "hub e celula nao podem dividir o mesmo /16 do supernet"
  }
}
