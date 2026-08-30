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
  network_account_id = "000000000000"
  target_account_ids = ["111111111111"]
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

  # module.cell tem seu PROPRIO data.aws_availability_zones.this — endereco distinto do da
  # raiz. Sem overrida-lo tambem, o plan inteiro falha aqui (o mock nao devolve nenhuma AZ e o
  # slice(0, 2) do modulo estoura), mesmo este run nao assertando nada sobre a celula.
  override_data {
    target = module.cell.data.aws_availability_zones.this
    values = {
      names = ["us-east-1a", "us-east-1b"]
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

  override_data {
    target = module.cell.data.aws_availability_zones.this
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

# Fase 3 — a celula le o hub SO por module.hub, nunca por valor fixo no codigo. Dois runs com
# valores diferentes, porque um override_module sozinho passaria mesmo se a celula tivesse o
# valor fixo no codigo igual ao injetado — a armadilha ja comprovada com name_servers.
run "cell_reads_the_transit_gateway_from_the_hub" {
  command = plan

  override_data {
    target = data.aws_availability_zones.this
    values = { names = ["us-east-1a", "us-east-1b"] }
  }

  override_data {
    target = module.cell.data.aws_availability_zones.this
    values = { names = ["us-east-1a", "us-east-1b"] }
  }

  override_module {
    target = module.hub
    outputs = {
      vpc_id                         = "vpc-aaaaaaaaaaaaaaaa1"
      vpc_cidr_block                 = "10.1.0.0/16"
      private_subnet_ids             = ["subnet-aaaa1", "subnet-aaaa2"]
      public_subnet_ids              = ["subnet-bbbb1", "subnet-bbbb2"]
      transit_gateway_id             = "tgw-aaaaaaaaaaaaaaaa1"
      transit_gateway_route_table_id = "tgw-rtb-aaaaaaaaaaaaaaaa1"
      transit_gateway_attachment_id  = "tgw-attach-aaaaaaaaaaaaaaaa1"
      alb_arn                        = "arn:aws:elasticloadbalancing:us-east-1:000000000000:loadbalancer/app/poc-hub-ingress/aaaa1"
      alb_listener_arn               = "arn:aws:elasticloadbalancing:us-east-1:000000000000:listener/app/poc-hub-ingress/aaaa1/aaaa1"
      alb_dns_name                   = "hub-aaaa1.us-east-1.elb.amazonaws.com"
      alb_zone_id                    = "Z35SXDOTRQ7X7K"
      alb_security_group_id          = "sg-aaaa1"
      client_vpn_endpoint_id         = "cvpn-endpoint-aaaa1"
      client_vpn_dns_name            = "aaaa1.cvpn.us-east-1.amazonaws.com"
      authorized_group_ids           = ["00000000-0000-0000-0000-000000000000"]
    }
  }

  assert {
    condition     = module.cell.transit_gateway_id_in_use == "tgw-aaaaaaaaaaaaaaaa1"
    error_message = "a celula tem de usar o TGW que o hub produziu"
  }
}

run "cell_follows_a_different_hub" {
  command = plan

  override_data {
    target = data.aws_availability_zones.this
    values = { names = ["us-east-1a", "us-east-1b"] }
  }

  override_data {
    target = module.cell.data.aws_availability_zones.this
    values = { names = ["us-east-1a", "us-east-1b"] }
  }

  override_module {
    target = module.hub
    outputs = {
      # os mesmos campos do run acima, com valores DIFERENTES — repetir por inteiro, nao
      # referenciar o run anterior: nenhum valor fixo no codigo satisfaz os dois.
      vpc_id                         = "vpc-ccccccccccccccc9"
      vpc_cidr_block                 = "10.9.0.0/16"
      private_subnet_ids             = ["subnet-cccc1", "subnet-cccc2"]
      public_subnet_ids              = ["subnet-dddd1", "subnet-dddd2"]
      transit_gateway_id             = "tgw-ccccccccccccccc9"
      transit_gateway_route_table_id = "tgw-rtb-ccccccccccccccc9"
      transit_gateway_attachment_id  = "tgw-attach-ccccccccccccccc9"
      alb_arn                        = "arn:aws:elasticloadbalancing:us-east-1:000000000000:loadbalancer/app/poc-hub-ingress/cccc9"
      alb_listener_arn               = "arn:aws:elasticloadbalancing:us-east-1:000000000000:listener/app/poc-hub-ingress/cccc9/cccc9"
      alb_dns_name                   = "hub-cccc9.us-east-1.elb.amazonaws.com"
      alb_zone_id                    = "Z35SXDOTRQ7X7K"
      alb_security_group_id          = "sg-cccc9"
      client_vpn_endpoint_id         = "cvpn-endpoint-cccc9"
      client_vpn_dns_name            = "cccc9.cvpn.us-east-1.amazonaws.com"
      authorized_group_ids           = ["00000000-0000-0000-0000-000000000000"]
    }
  }

  assert {
    condition     = module.cell.transit_gateway_id_in_use == "tgw-ccccccccccccccc9"
    error_message = "o TGW tem de vir do hub, nao estar fixo no codigo da celula"
  }

  assert {
    condition     = module.cell.api_authorized_cidr == "10.9.0.0/16"
    error_message = "o SG do cluster tem de autorizar 443 a partir do CIDR da VPC HUB — o Client VPN faz SNAT"
  }
}

# mock_provider "helm" nao simula a key (namespace, name) de releases: duas releases com o mesmo
# nome passam verdes offline e so explodem no apply real com "cannot re-use a name that is still
# in use". Ja aconteceu com target_group_binding e o gateway do ingress_istio.
run "helm_release_names_do_not_collide" {
  command = plan

  override_data {
    target = data.aws_availability_zones.this
    values = { names = ["us-east-1a", "us-east-1b"] }
  }

  override_data {
    target = module.cell.data.aws_availability_zones.this
    values = { names = ["us-east-1a", "us-east-1b"] }
  }

  assert {
    condition     = length(toset(module.cell.helm_release_names)) == length(module.cell.helm_release_names)
    error_message = "duas releases com o mesmo nome no mesmo namespace: o mock nao pega isso, o apply real morre com 'cannot re-use a name that is still in use'"
  }
}
