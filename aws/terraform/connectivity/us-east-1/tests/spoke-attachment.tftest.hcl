# 2.3 — o lado do hub do attachment com a spoke. Sem isto o TGW e o tgw-rt-hub de connectivity
# existem mas ficam órfãos: nenhum attachment liga a própria VPC hub a eles, e o tráfego que
# chega pelo túnel na subnet privada do hub não tem como sair para o TGW.

mock_provider "aws" {}

variables {
  base_domain        = "exemplo.com"
  operator_group_ids = ["11111111-2222-3333-4444-555555555555"]
  saml_metadata_path = "tests/fixtures/saml-metadata.xml"
  spoke_account_ids  = ["222222222222", "333333333333"]
}

override_data {
  target = data.aws_vpc.hub
  values = {
    id = "vpc-hub000000000001"
  }
}

override_data {
  target = data.aws_subnets.hub_private
  values = {
    ids = ["subnet-priv0000000a", "subnet-priv0000000b"]
  }
}

override_data {
  target = data.aws_route53_zone.subzone
  values = {
    zone_id = "ZSUBZONE00000000001"
  }
}

override_data {
  target = data.aws_route_table.hub_private
  values = {
    id = "rtb-hubprivate00001"
  }
}

override_data {
  target = data.aws_route_table.hub_public
  values = {
    id = "rtb-hubpublic000001"
  }
}

# Mesma razão do override global em isolation.tftest.hcl: sem um arn válido aqui,
# aws_ram_resource_association falha na validação de schema do provider (client-side, sob
# mock) por um motivo que nada tem a ver com o que cada run pretende testar.
override_resource {
  target = aws_ec2_transit_gateway.hub
  values = {
    arn = "arn:aws:ec2:us-east-1:000000000000:transit-gateway/tgw-0000000000000000f"
  }
}

# --------------------------------------------------------------------------------------
# RAM — pré-requisito do attachment cross-conta
# --------------------------------------------------------------------------------------

run "o_share_nao_permite_principal_externo" {
  command = plan

  assert {
    condition     = aws_ram_resource_share.tgw.allow_external_principals == false
    error_message = "o share tem de ficar dentro da Organization, recebido ${aws_ram_resource_share.tgw.allow_external_principals}"
  }
}

run "uma_principal_association_por_conta_spoke" {
  command = plan

  assert {
    condition     = length(aws_ram_principal_association.spoke) == 2
    error_message = "deveria haver uma principal association por conta em spoke_account_ids (2), há ${length(aws_ram_principal_association.spoke)}"
  }

  assert {
    condition = toset([for a in aws_ram_principal_association.spoke : a.principal]) == toset([
      "222222222222", "333333333333"
    ])
    error_message = "as principal associations deveriam ser pelas contas de spoke_account_ids, recebido ${jsonencode([for a in aws_ram_principal_association.spoke : a.principal])}"
  }
}

# Segundo conjunto, tamanho diferente: uma lista fixa no código passaria no run anterior e
# cairia aqui.
run "e_acompanha_outra_lista_de_contas" {
  command = plan

  variables {
    spoke_account_ids = ["444444444444"]
  }

  assert {
    condition     = length(aws_ram_principal_association.spoke) == 1
    error_message = "trocando spoke_account_ids, as principal associations deveriam acompanhar — há ${length(aws_ram_principal_association.spoke)}"
  }

  assert {
    condition     = one(values(aws_ram_principal_association.spoke)).principal == "444444444444"
    error_message = "recebido ${one(values(aws_ram_principal_association.spoke)).principal}"
  }
}

# --------------------------------------------------------------------------------------
# Attachment da própria VPC hub
# --------------------------------------------------------------------------------------

run "o_hub_se_anexa_ao_proprio_tgw_sem_defaults_automaticos" {
  command = plan

  assert {
    condition     = aws_ec2_transit_gateway_vpc_attachment.hub.vpc_id == "vpc-hub000000000001"
    error_message = "o attachment deveria ser da VPC hub lida por tag, recebido ${aws_ec2_transit_gateway_vpc_attachment.hub.vpc_id}"
  }

  assert {
    condition = toset(aws_ec2_transit_gateway_vpc_attachment.hub.subnet_ids) == toset([
      "subnet-priv0000000a", "subnet-priv0000000b"
    ])
    error_message = "o attachment deveria usar as subnets privadas do hub, recebido ${jsonencode(aws_ec2_transit_gateway_vpc_attachment.hub.subnet_ids)}"
  }

  # Mesma disciplina do TGW: nada entra por default, tudo por associação/propagação explícita.
  assert {
    condition     = aws_ec2_transit_gateway_vpc_attachment.hub.transit_gateway_default_route_table_association == false
    error_message = "transit_gateway_default_route_table_association tem de ser false"
  }

  assert {
    condition     = aws_ec2_transit_gateway_vpc_attachment.hub.transit_gateway_default_route_table_propagation == false
    error_message = "transit_gateway_default_route_table_propagation tem de ser false"
  }
}

run "o_attachment_do_hub_e_associado_a_tgw_rt_hub" {
  command = plan

  override_resource {
    target          = aws_ec2_transit_gateway_route_table.hub
    override_during = plan
    values = {
      id = "tgw-rtb-hub00000001"
    }
  }

  override_resource {
    target          = aws_ec2_transit_gateway_vpc_attachment.hub
    override_during = plan
    values = {
      id = "tgw-attach-hub00001"
    }
  }

  assert {
    condition     = aws_ec2_transit_gateway_route_table_association.hub.transit_gateway_route_table_id == "tgw-rtb-hub00000001"
    error_message = "a associação deveria apontar para tgw-rt-hub, recebido ${aws_ec2_transit_gateway_route_table_association.hub.transit_gateway_route_table_id}"
  }

  assert {
    condition     = aws_ec2_transit_gateway_route_table_association.hub.transit_gateway_attachment_id == "tgw-attach-hub00001"
    error_message = "a associação deveria ser do attachment do hub, recebido ${aws_ec2_transit_gateway_route_table_association.hub.transit_gateway_attachment_id}"
  }
}

# --------------------------------------------------------------------------------------
# Rota no lado do hub — uma só, para o supernet inteiro
# --------------------------------------------------------------------------------------

run "a_rota_do_hub_para_o_tgw_e_do_supernet_inteiro" {
  command = plan

  override_resource {
    target          = aws_ec2_transit_gateway.hub
    override_during = plan
    values = {
      id  = "tgw-aaaaaaaaaaaaaaaa1"
      arn = "arn:aws:ec2:us-east-1:000000000000:transit-gateway/tgw-aaaaaaaaaaaaaaaa1"
    }
  }

  assert {
    condition     = aws_route.hub_to_tgw.destination_cidr_block == "10.0.0.0/12"
    error_message = "a rota deveria ser do supernet, recebido ${aws_route.hub_to_tgw.destination_cidr_block}"
  }

  assert {
    condition     = aws_route.hub_to_tgw.transit_gateway_id == "tgw-aaaaaaaaaaaaaaaa1"
    error_message = "a rota deveria apontar para o TGW desta raiz, recebido ${aws_route.hub_to_tgw.transit_gateway_id}"
  }

  assert {
    condition     = aws_route.hub_to_tgw.route_table_id == "rtb-hubprivate00001"
    error_message = "a rota deveria ir na route table privada do hub, recebido ${aws_route.hub_to_tgw.route_table_id}"
  }

  # A PÚBLICA também, e não é redundância: é nela que vive o ALB de ingress. Sem esta rota o
  # health check do hub para os endereços fixos do NLB da célula não tem caminho de ida, e o
  # sintoma é target `unhealthy` com `Request timed out` enquanto o target group DA SPOKE está
  # `healthy` — o que se lê, errado, como problema de security group. Visto no aceite do 3.2.
  assert {
    condition     = aws_route.hub_public_to_tgw.route_table_id == "rtb-hubpublic000001"
    error_message = "a rota pública deveria ir na route table pública do hub, recebido ${aws_route.hub_public_to_tgw.route_table_id}"
  }

  assert {
    condition     = aws_route.hub_public_to_tgw.route_table_id != aws_route.hub_to_tgw.route_table_id
    error_message = "as duas rotas do hub estão na mesma tabela — uma das duas metades do hub fica sem caminho"
  }

  assert {
    condition     = aws_route.hub_public_to_tgw.destination_cidr_block == "10.0.0.0/12"
    error_message = "a rota pública cobre o supernet, recebido ${aws_route.hub_public_to_tgw.destination_cidr_block}"
  }

  assert {
    condition     = aws_route.hub_public_to_tgw.transit_gateway_id == "tgw-aaaaaaaaaaaaaaaa1"
    error_message = "a rota pública tem de apontar para o TGW desta raiz, recebido ${aws_route.hub_public_to_tgw.transit_gateway_id}"
  }
}

run "e_acompanha_outra_route_table_privada" {
  command = plan

  override_data {
    target = data.aws_route_table.hub_private
    values = {
      id = "rtb-outra00000000002"
    }
  }

  assert {
    condition     = aws_route.hub_to_tgw.route_table_id == "rtb-outra00000000002"
    error_message = "trocando a route table lida, a rota deveria acompanhar — recebido ${aws_route.hub_to_tgw.route_table_id}"
  }
}
