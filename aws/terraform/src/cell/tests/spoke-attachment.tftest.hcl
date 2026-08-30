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
  vpc_cidr            = "10.2.0.0/16"
  target_account_ids  = ["000000000000"]
  network_account_id  = "111111111111"
  public_access_cidrs = ["203.0.113.10/32"]

  # 3.2 tornou base_domain obrigatoria (sem default, falha-fechado). Ela nao tem
  # relacao com o que este arquivo testa — sem o valor, nenhum run deste arquivo executa.
  base_domain = "exemplo.com"

  # O hub, por referencia — ver o comentario no variables.tf do modulo. hub_vpc_cidr_block
  # precisa ser CIDR real: alimenta a validacao client-side do provider na regra de 443.
  hub_vpc_id                         = "vpc-hub000000000001"
  hub_vpc_cidr_block                 = "10.1.0.0/16"
  transit_gateway_id                 = "tgw-hub00000000001"
  hub_transit_gateway_route_table_id = "tgw-rtb-hub00000001"
  hub_transit_gateway_attachment_id  = "tgw-attach-hub00001"
  hub_alb_listener_arn               = "arn:aws:elasticloadbalancing:us-east-1:111111111111:listener/app/poc-hub-ingress/0000000000000001/aaaaaaaaaaaaaaaa"
  hub_alb_dns_name                   = "poc-hub-ingress-000000001.us-east-1.elb.amazonaws.com"
  hub_alb_zone_id                    = "Z35SXDOTRQ7X7K"
}

# As AZs vêm de data.aws_availability_zones (indexado por module.network); sob mock o valor é
# sintético e o plan morre — override em todo arquivo de teste da raiz.
override_data {
  target = data.aws_availability_zones.this
  values = {
    names = ["us-east-1a", "us-east-1b"]
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

  variables {
    transit_gateway_id = "tgw-outro00000000002"
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

# A rota da malha existe nas DUAS tabelas da spoke, e isso não é redundância: `module.cluster`
# recebe as 4 subnets (`control_plane_subnet_ids`) e a AWS escolhe onde põe as ENIs do endpoint
# privado. No apply de 2026-08-28 elas caíram nas PÚBLICAS, o retorno para o hub seguiu o IGW e
# os dois helm_release morreram com `i/o timeout`. Os applies anteriores passaram por sorte.
#
# Dois overrides com IDs DIFERENTES, e não um: com um só, uma implementação que mandasse as duas
# rotas para a mesma tabela passaria — é a lição do `1.3` (um override prova o valor, dois provam
# a ligação).
run "a_rota_da_malha_existe_nas_duas_tabelas_da_spoke" {
  command = plan

  override_resource {
    target          = module.network.aws_route_table.private
    override_during = plan
    values = {
      id = "rtb-spoke-private01"
    }
  }

  override_resource {
    target          = module.network.aws_route_table.public
    override_during = plan
    values = {
      id = "rtb-spoke-public99"
    }
  }

  assert {
    condition     = aws_route.spoke_to_hub_public.route_table_id == "rtb-spoke-public99"
    error_message = "a segunda rota deveria ir na route table PÚBLICA, recebido ${aws_route.spoke_to_hub_public.route_table_id}"
  }

  assert {
    condition     = aws_route.spoke_to_hub_public.route_table_id != aws_route.spoke_to_hub.route_table_id
    error_message = "as duas rotas estão na mesma route table — as ENIs numa das duas ficaria sem caminho de volta"
  }

  assert {
    condition     = aws_route.spoke_to_hub_public.destination_cidr_block == "10.0.0.0/12"
    error_message = "a rota pública tem de cobrir o supernet inteiro, recebido ${aws_route.spoke_to_hub_public.destination_cidr_block}"
  }

  assert {
    condition     = aws_route.spoke_to_hub_public.transit_gateway_id == "tgw-hub00000000001"
    error_message = "a rota pública tem de apontar para o TGW do hub, recebido ${aws_route.spoke_to_hub_public.transit_gateway_id}"
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
