# O que a raiz decide, em teste: o recorte das AZs (duas, para o Client VPN e o NLB da celula) e
# a nao-sobreposicao dos CIDRs do hub e da celula. A ligacao hub->celula entra na fase 3; aqui a
# celula ainda nem existe, entao so se asserta o que ja e decidido.

mock_provider "aws" {}
mock_provider "aws" { alias = "network" }

variables {
  base_domain        = "exemplo.com"
  admin_group_ids    = {}
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
    arn = "arn:aws:ec2:us-west-2:000000000000:transit-gateway/tgw-0000000000000000f"
  }
}

# Tres AZs disponiveis, o hub fica com as DUAS primeiras — slice, nao a lista inteira. Duas porque
# o Client VPN associa uma target network por AZ e o NLB interno da celula fixa um IP por AZ.
run "hub_gets_the_first_two_availability_zones" {
  command = plan

  override_data {
    target = data.aws_availability_zones.network
    values = {
      names = ["us-west-2a", "us-west-2b", "us-west-2c"]
    }
  }

  # data.aws_availability_zones.cell alimenta module.cell (var.availability_zones), num data
  # source SEPARADO do que alimenta o hub — achado da revisao final: os dois resolviam antes num
  # unico data source sem provider explicito, que sempre roda na conta default (cicd), fazendo o
  # hub herdar AZs resolvidas na conta ERRADA (aplica na network). Sem overridar tambem este, o
  # mock nao devolve nenhuma AZ e o slice(0, 2) do modulo estoura, mesmo este run nao assertando
  # nada sobre a celula.
  override_data {
    target = data.aws_availability_zones.cell
    values = {
      names = ["us-west-2a", "us-west-2b"]
    }
  }

  assert {
    condition     = length(local.hub_availability_zones) == 2
    error_message = "o hub tem de receber DUAS AZs, recebido ${length(local.hub_availability_zones)}"
  }

  # Nao basta a contagem: as duas tem de ser as PRIMEIRAS da lista. Um slice (2, 4) passaria na
  # contagem e escolheria AZs erradas sem ninguem perceber no plan.
  assert {
    condition     = toset(local.hub_availability_zones) == toset(["us-west-2a", "us-west-2b"])
    error_message = "as AZs tem de ser as duas primeiras da regiao, recebido ${jsonencode(local.hub_availability_zones)}"
  }
}

run "hub_and_cell_cidrs_do_not_overlap" {
  command = plan

  override_data {
    target = data.aws_availability_zones.network
    values = {
      names = ["us-west-2a", "us-west-2b"]
    }
  }

  override_data {
    target = data.aws_availability_zones.cell
    values = {
      names = ["us-west-2a", "us-west-2b"]
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
    target = data.aws_availability_zones.network
    values = { names = ["us-west-2a", "us-west-2b"] }
  }

  override_data {
    target = data.aws_availability_zones.cell
    values = { names = ["us-west-2a", "us-west-2b"] }
  }

  override_module {
    target = module.hub
    outputs = {
      vpc_id                         = "vpc-aaaaaaaaaaaaaaaa1"
      vpc_cidr_block                 = "10.4.0.0/16"
      private_subnet_ids             = ["subnet-aaaa1", "subnet-aaaa2"]
      public_subnet_ids              = ["subnet-bbbb1", "subnet-bbbb2"]
      transit_gateway_id             = "tgw-aaaaaaaaaaaaaaaa1"
      transit_gateway_route_table_id = "tgw-rtb-aaaaaaaaaaaaaaaa1"
      transit_gateway_attachment_id  = "tgw-attach-aaaaaaaaaaaaaaaa1"
      alb_arn                        = "arn:aws:elasticloadbalancing:us-west-2:000000000000:loadbalancer/app/poc-hub-ingress/aaaa1"
      alb_listener_arn               = "arn:aws:elasticloadbalancing:us-west-2:000000000000:listener/app/poc-hub-ingress/aaaa1/aaaa1"
      alb_dns_name                   = "hub-aaaa1.us-west-2.elb.amazonaws.com"
      alb_zone_id                    = "Z35SXDOTRQ7X7K"
      alb_security_group_id          = "sg-aaaa1"
      client_vpn_endpoint_id         = "cvpn-endpoint-aaaa1"
      client_vpn_dns_name            = "aaaa1.cvpn.us-west-2.amazonaws.com"
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
    target = data.aws_availability_zones.network
    values = { names = ["us-west-2a", "us-west-2b"] }
  }

  override_data {
    target = data.aws_availability_zones.cell
    values = { names = ["us-west-2a", "us-west-2b"] }
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
      alb_arn                        = "arn:aws:elasticloadbalancing:us-west-2:000000000000:loadbalancer/app/poc-hub-ingress/cccc9"
      alb_listener_arn               = "arn:aws:elasticloadbalancing:us-west-2:000000000000:listener/app/poc-hub-ingress/cccc9/cccc9"
      alb_dns_name                   = "hub-cccc9.us-west-2.elb.amazonaws.com"
      alb_zone_id                    = "Z35SXDOTRQ7X7K"
      alb_security_group_id          = "sg-cccc9"
      client_vpn_endpoint_id         = "cvpn-endpoint-cccc9"
      client_vpn_dns_name            = "cccc9.cvpn.us-west-2.amazonaws.com"
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
# Guard de regressao do bug que o controller pegou a mao (nao os reviewers) no preflight da
# Task 3: um `name = "control-plane"` literal, sem regiao, na composicao da raiz — bloqueante,
# porque criaria 5 roles de IAM e 2 records de Route 53 sem qualificacao regional. Nenhum teste
# cobria isso ate aqui.
run "cell_name_carries_the_region" {
  command = plan

  override_data {
    target = data.aws_availability_zones.network
    values = { names = ["us-west-2a", "us-west-2b"] }
  }

  override_data {
    target = data.aws_availability_zones.cell
    values = { names = ["us-west-2a", "us-west-2b"] }
  }

  assert {
    condition     = module.cell.cluster_name == "control-plane-us-west-2"
    error_message = "o nome da celula tem de carregar a regiao: recursos globais (IAM roles, Route 53) colidem entre regioes sem isso"
  }
}

run "helm_release_names_do_not_collide" {
  command = plan

  override_data {
    target = data.aws_availability_zones.network
    values = { names = ["us-west-2a", "us-west-2b"] }
  }

  override_data {
    target = data.aws_availability_zones.cell
    values = { names = ["us-west-2a", "us-west-2b"] }
  }

  assert {
    condition     = length(toset(module.cell.helm_release_names)) == length(module.cell.helm_release_names)
    error_message = "duas releases com o mesmo nome no mesmo namespace: o mock nao pega isso, o apply real morre com 'cannot re-use a name that is still in use'"
  }
}

# Achado na sessao 2026-08-31: regions/<regiao> nunca repassava estas duas variaveis para
# module.cell — o break-glass documentado no README.md ficava sem efeito desde a consolidacao
# da ADR 0014 (editar values.tfvars so produzia warning de variavel nao declarada aqui).
run "endpoint_publico_nasce_fechado" {
  command = plan

  override_data {
    target = data.aws_availability_zones.network
    values = { names = ["us-west-2a", "us-west-2b"] }
  }

  override_data {
    target = data.aws_availability_zones.cell
    values = { names = ["us-west-2a", "us-west-2b"] }
  }

  assert {
    condition     = module.cell.endpoint_public_access == false
    error_message = "o default tem de ser fechado, recebido ${module.cell.endpoint_public_access}"
  }
}

run "endpoint_publico_repassa_o_cidr_ate_o_cluster" {
  command = plan

  variables {
    endpoint_public_access = true
    public_access_cidrs    = ["203.0.113.10/32"]
  }

  override_data {
    target = data.aws_availability_zones.network
    values = { names = ["us-west-2a", "us-west-2b"] }
  }

  override_data {
    target = data.aws_availability_zones.cell
    values = { names = ["us-west-2a", "us-west-2b"] }
  }

  assert {
    condition     = module.cell.endpoint_public_access == true
    error_message = "o flag do root deveria chegar a module.cell, recebido ${module.cell.endpoint_public_access}"
  }

  assert {
    condition     = module.cell.public_access_cidrs == toset(["203.0.113.10/32"])
    error_message = "o CIDR do root deveria chegar a module.cell, recebido ${jsonencode(module.cell.public_access_cidrs)}"
  }
}

# admin_group_ids: issue #71. Quatro casos — default vazio, um permission set, dois permission
# sets fundidos com admin_principal_arns, e bootstrap ausente (postcondition falha).

run "admin_group_ids_default_vazio_nao_cria_data_source" {
  command = plan

  # values.auto.tfvars (o symlink real) ja declara admin_principal_arns nao-vazio para esta conta;
  # zerar aqui isola o que este run quer provar (admin_group_ids sozinho).
  variables {
    admin_principal_arns = []
  }

  override_data {
    target = data.aws_availability_zones.network
    values = { names = ["us-west-2a", "us-west-2b"] }
  }

  override_data {
    target = data.aws_availability_zones.cell
    values = { names = ["us-west-2a", "us-west-2b"] }
  }

  assert {
    condition     = length(local.admin_group_access_entries) == 0
    error_message = "sem admin_group_ids nenhuma access entry deveria vir do Identity Center, recebido ${jsonencode(local.admin_group_access_entries)}"
  }

  assert {
    condition     = toset(keys(merge(local.admin_principal_access_entries, local.admin_group_access_entries))) == toset([])
    error_message = "com admin_principal_arns e admin_group_ids default vazios, access_entries devia ficar vazio, recebido ${jsonencode(keys(merge(local.admin_principal_access_entries, local.admin_group_access_entries)))}"
  }
}

run "admin_group_ids_um_permission_set_resolve_a_role_sso" {
  command = plan

  variables {
    admin_group_ids = {
      PlatformAdmin = "00000000-0000-0000-0000-000000000000"
    }
  }

  override_data {
    target = data.aws_availability_zones.network
    values = { names = ["us-west-2a", "us-west-2b"] }
  }

  override_data {
    target = data.aws_availability_zones.cell
    values = { names = ["us-west-2a", "us-west-2b"] }
  }

  # override_data com for_each exige a chave no target (probado): sem ela nao resolve.
  override_data {
    target = data.aws_iam_roles.admin_group["PlatformAdmin"]
    values = {
      arns = ["arn:aws:iam::270222614208:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_PlatformAdmin_aaaaaaaaaaaaaaaa"]
    }
  }

  assert {
    condition     = length(local.admin_group_access_entries) == 1
    error_message = "um permission set deveria produzir exatamente 1 access entry, recebido ${jsonencode(local.admin_group_access_entries)}"
  }

  assert {
    condition     = local.admin_group_access_entries["PlatformAdmin"].principal_arn == "arn:aws:iam::270222614208:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_PlatformAdmin_aaaaaaaaaaaaaaaa"
    error_message = "o ARN resolvido tem de manter o path /aws-reserved/sso.amazonaws.com/ — EKS access entries aceita path, remover quebraria a rastreabilidade"
  }
}

run "admin_group_ids_dois_permission_sets_fundem_com_admin_principal_arns" {
  command = plan

  variables {
    admin_principal_arns = ["arn:aws:iam::270222614208:role/OrganizationAccountAccessRole"]
    admin_group_ids = {
      PlatformAdmin       = "00000000-0000-0000-0000-000000000000"
      UserDiscoveryDevOps = "11111111-1111-1111-1111-111111111111"
    }
  }

  override_data {
    target = data.aws_availability_zones.network
    values = { names = ["us-west-2a", "us-west-2b"] }
  }

  override_data {
    target = data.aws_availability_zones.cell
    values = { names = ["us-west-2a", "us-west-2b"] }
  }

  override_data {
    target = data.aws_iam_roles.admin_group["PlatformAdmin"]
    values = {
      arns = ["arn:aws:iam::270222614208:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_PlatformAdmin_aaaaaaaaaaaaaaaa"]
    }
  }

  override_data {
    target = data.aws_iam_roles.admin_group["UserDiscoveryDevOps"]
    values = {
      arns = ["arn:aws:iam::270222614208:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_Viewer_bbbbbbbbbbbbbbbb"]
    }
  }

  assert {
    condition     = length(merge(local.admin_principal_access_entries, local.admin_group_access_entries)) == 3
    error_message = "1 principal + 2 grupos deveria fundir em 3 access entries, recebido ${jsonencode(keys(merge(local.admin_principal_access_entries, local.admin_group_access_entries)))}"
  }

  assert {
    condition     = toset(keys(merge(local.admin_principal_access_entries, local.admin_group_access_entries))) == toset(["arn:aws:iam::270222614208:role/OrganizationAccountAccessRole", "PlatformAdmin", "UserDiscoveryDevOps"])
    error_message = "as chaves tem de ser o ARN (fonte admin_principal_arns) e o nome do permission set (fonte admin_group_ids), recebido ${jsonencode(keys(merge(local.admin_principal_access_entries, local.admin_group_access_entries)))}"
  }
}

run "admin_group_ids_sem_bootstrap_falha_no_postcondition" {
  command = plan

  variables {
    admin_group_ids = {
      PlatformAdmin = "00000000-0000-0000-0000-000000000000"
    }
  }

  override_data {
    target = data.aws_availability_zones.network
    values = { names = ["us-west-2a", "us-west-2b"] }
  }

  override_data {
    target = data.aws_availability_zones.cell
    values = { names = ["us-west-2a", "us-west-2b"] }
  }

  override_data {
    target = data.aws_iam_roles.admin_group["PlatformAdmin"]
    values = {
      arns = []
    }
  }

  expect_failures = [
    data.aws_iam_roles.admin_group,
  ]
}
