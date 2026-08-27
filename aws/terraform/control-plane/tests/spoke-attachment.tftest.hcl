# 2.3 — o lado da spoke do attachment com o TGW do hub. Sem isto o túnel alcança a VPC hub e
# para aí: nada liga a VPC desta camada (conta cicd) ao TGW da conta network.

mock_provider "aws" {}

mock_provider "aws" {
  alias = "network"
}

mock_provider "kubernetes" {}
mock_provider "helm" {}

variables {
  name                = "control-plane"
  region              = "us-east-1"
  aws_profile         = "cicd"
  network_profile     = "network"
  hub_vpc_name        = "poc-hub-vpc"
  vpc_cidr            = "10.2.0.0/16"
  availability_zones  = ["us-east-1a", "us-east-1b"]
  target_account_ids  = ["000000000000"]
  network_account_id  = "111111111111"
  public_access_cidrs = ["203.0.113.10/32"]
}

# Data sources de provider devolvem valor sintético sob mock — sem override a asserção passaria
# sem verificar a ligação real (mesma disciplina de connectivity/tests/spoke-attachment.tftest.hcl).
override_data {
  target = data.aws_ec2_transit_gateway.hub
  values = {
    id = "tgw-hub00000000001"
  }
}

override_data {
  target = data.aws_ec2_transit_gateway_route_table.hub
  values = {
    id = "tgw-rtb-hub00000001"
  }
}

override_data {
  target = data.aws_ec2_transit_gateway_vpc_attachment.hub
  values = {
    id = "tgw-attach-hub00001"
  }
}

# --------------------------------------------------------------------------------------
# Attachment da spoke
# --------------------------------------------------------------------------------------

run "a_spoke_se_anexa_ao_tgw_do_hub_sem_defaults_automaticos" {
  command = plan

  assert {
    condition     = aws_ec2_transit_gateway_vpc_attachment.this.transit_gateway_id == "tgw-hub00000000001"
    error_message = "o attachment deveria usar o TGW lido por tag na conta network, recebido ${aws_ec2_transit_gateway_vpc_attachment.this.transit_gateway_id}"
  }

  assert {
    condition     = aws_ec2_transit_gateway_vpc_attachment.this.transit_gateway_default_route_table_association == false
    error_message = "transit_gateway_default_route_table_association tem de ser false"
  }

  assert {
    condition     = aws_ec2_transit_gateway_vpc_attachment.this.transit_gateway_default_route_table_propagation == false
    error_message = "transit_gateway_default_route_table_propagation tem de ser false"
  }
}

run "e_acompanha_outro_tgw" {
  command = plan

  override_data {
    target = data.aws_ec2_transit_gateway.hub
    values = {
      id = "tgw-outro00000000002"
    }
  }

  assert {
    condition     = aws_ec2_transit_gateway_vpc_attachment.this.transit_gateway_id == "tgw-outro00000000002"
    error_message = "trocando o TGW lido, o attachment deveria acompanhar — recebido ${aws_ec2_transit_gateway_vpc_attachment.this.transit_gateway_id}"
  }
}

# --------------------------------------------------------------------------------------
# tgw-rt-spoke — vive no state da spoke, mas na conta do hub (provider aliasado)
# --------------------------------------------------------------------------------------

run "a_route_table_da_spoke_pertence_ao_tgw_do_hub" {
  command = plan

  assert {
    condition     = aws_ec2_transit_gateway_route_table.spoke.transit_gateway_id == "tgw-hub00000000001"
    error_message = "recebido ${aws_ec2_transit_gateway_route_table.spoke.transit_gateway_id}"
  }
}

run "o_attachment_da_spoke_e_associado_a_tgw_rt_spoke" {
  command = plan

  override_resource {
    target          = aws_ec2_transit_gateway_route_table.spoke
    override_during = plan
    values = {
      id = "tgw-rtb-spoke0001"
    }
  }

  override_resource {
    target          = aws_ec2_transit_gateway_vpc_attachment.this
    override_during = plan
    values = {
      id = "tgw-attach-spoke01"
    }
  }

  assert {
    condition     = aws_ec2_transit_gateway_route_table_association.spoke.transit_gateway_route_table_id == "tgw-rtb-spoke0001"
    error_message = "recebido ${aws_ec2_transit_gateway_route_table_association.spoke.transit_gateway_route_table_id}"
  }

  assert {
    condition     = aws_ec2_transit_gateway_route_table_association.spoke.transit_gateway_attachment_id == "tgw-attach-spoke01"
    error_message = "recebido ${aws_ec2_transit_gateway_route_table_association.spoke.transit_gateway_attachment_id}"
  }
}

# --------------------------------------------------------------------------------------
# As duas propagações — não podem estar trocadas entre si (mesmo tipo/formato nas duas
# pontas, fácil de inverter sem que uma asserção de valor perceba).
# --------------------------------------------------------------------------------------

run "propagacao_spoke_para_hub_ensina_o_hub_a_alcancar_a_spoke" {
  command = plan

  override_resource {
    target          = aws_ec2_transit_gateway_vpc_attachment.this
    override_during = plan
    values = {
      id = "tgw-attach-spoke01"
    }
  }

  assert {
    condition     = aws_ec2_transit_gateway_route_table_propagation.spoke_to_hub.transit_gateway_attachment_id == "tgw-attach-spoke01"
    error_message = "a propagacao spoke->hub deveria ser do attachment da spoke, recebido ${aws_ec2_transit_gateway_route_table_propagation.spoke_to_hub.transit_gateway_attachment_id}"
  }

  assert {
    condition     = aws_ec2_transit_gateway_route_table_propagation.spoke_to_hub.transit_gateway_route_table_id == "tgw-rtb-hub00000001"
    error_message = "a propagacao spoke->hub deveria ir para tgw-rt-hub, recebido ${aws_ec2_transit_gateway_route_table_propagation.spoke_to_hub.transit_gateway_route_table_id}"
  }
}

run "propagacao_hub_para_spoke_ensina_a_spoke_a_alcancar_o_hub" {
  command = plan

  override_resource {
    target          = aws_ec2_transit_gateway_route_table.spoke
    override_during = plan
    values = {
      id = "tgw-rtb-spoke0001"
    }
  }

  assert {
    condition     = aws_ec2_transit_gateway_route_table_propagation.hub_to_spoke.transit_gateway_attachment_id == "tgw-attach-hub00001"
    error_message = "a propagacao hub->spoke deveria ser do attachment do hub, recebido ${aws_ec2_transit_gateway_route_table_propagation.hub_to_spoke.transit_gateway_attachment_id}"
  }

  assert {
    condition     = aws_ec2_transit_gateway_route_table_propagation.hub_to_spoke.transit_gateway_route_table_id == "tgw-rtb-spoke0001"
    error_message = "a propagacao hub->spoke deveria ir para tgw-rt-spoke, recebido ${aws_ec2_transit_gateway_route_table_propagation.hub_to_spoke.transit_gateway_route_table_id}"
  }
}

# --------------------------------------------------------------------------------------
# Rota de volta, no lado da spoke
# --------------------------------------------------------------------------------------

run "a_rota_da_spoke_para_o_supernet_usa_o_tgw" {
  command = plan

  override_resource {
    target          = module.network.aws_route_table.private
    override_during = plan
    values = {
      id = "rtb-spoke-private01"
    }
  }

  assert {
    condition     = aws_route.spoke_to_hub.destination_cidr_block == "10.0.0.0/12"
    error_message = "recebido ${aws_route.spoke_to_hub.destination_cidr_block}"
  }

  assert {
    condition     = aws_route.spoke_to_hub.transit_gateway_id == "tgw-hub00000000001"
    error_message = "recebido ${aws_route.spoke_to_hub.transit_gateway_id}"
  }

  assert {
    condition     = aws_route.spoke_to_hub.route_table_id == "rtb-spoke-private01"
    error_message = "a rota deveria ir na route table privada desta spoke, recebido ${aws_route.spoke_to_hub.route_table_id}"
  }
}

# --------------------------------------------------------------------------------------
# O TGW nasce com AutoAcceptSharedAttachments = disable — o attachment cross-conta fica em
# pendingAcceptance até o dono do TGW (conta network) aceitar explicitamente. RAM só resolve
# o convite de compartilhamento, não este aceite; são dois mecanismos distintos.
# --------------------------------------------------------------------------------------

run "o_attachment_e_aceito_do_lado_do_dono_do_tgw" {
  command = plan

  override_resource {
    target          = aws_ec2_transit_gateway_vpc_attachment.this
    override_during = plan
    values = {
      id = "tgw-attach-spoke01"
    }
  }

  assert {
    condition     = aws_ec2_transit_gateway_vpc_attachment_accepter.this.transit_gateway_attachment_id == "tgw-attach-spoke01"
    error_message = "o accepter deveria ser do attachment desta spoke, recebido ${aws_ec2_transit_gateway_vpc_attachment_accepter.this.transit_gateway_attachment_id}"
  }
}

run "o_accepter_nao_briga_com_o_attachment_pelos_defaults" {
  command = plan

  assert {
    condition     = aws_ec2_transit_gateway_vpc_attachment_accepter.this.transit_gateway_default_route_table_association == false
    error_message = "recebido ${aws_ec2_transit_gateway_vpc_attachment_accepter.this.transit_gateway_default_route_table_association}"
  }

  assert {
    condition     = aws_ec2_transit_gateway_vpc_attachment_accepter.this.transit_gateway_default_route_table_propagation == false
    error_message = "recebido ${aws_ec2_transit_gateway_vpc_attachment_accepter.this.transit_gateway_default_route_table_propagation}"
  }
}
