# O que estes testes protegem é a propriedade que não se vê olhando o apply dar certo: um TGW
# com os defaults ligados sobe igual, conecta igual, e só na primeira spoke↔spoke indevida
# alguém descobre. Aqui o vermelho vem antes de qualquer recurso existir.

mock_provider "aws" {}

variables {
  base_domain        = "exemplo.com"
  operator_group_ids = ["11111111-2222-3333-4444-555555555555"]
  region             = "us-east-1"
  vpc_cidr           = "10.1.0.0/16"
  availability_zones = ["a", "b"]
  saml_metadata_path = "tests/fixtures/saml-metadata.xml"
  spoke_account_ids  = ["222222222222"]
}

# Data sources de provider devolvem valor sintético sob mock — asserção sobre eles passaria
# sem verificar nada. Estes overrides fazem as ligações serem reais no plan. O que era
# descoberto por tag agora é produzido pelo submodulo network, então vira override_module.
override_module {
  target = module.network

  outputs = {
    vpc_id                 = "vpc-hub000000000001"
    vpc_cidr               = "10.1.0.0/16"
    private_subnet_ids     = ["subnet-priv0000000a", "subnet-priv0000000b"]
    public_subnet_ids      = ["subnet-pub00000000a", "subnet-pub00000000b"]
    private_route_table_id = "rtb-hubprivate00001"
    public_route_table_id  = "rtb-hubpublic000001"
  }
}

override_data {
  target = data.aws_route53_zone.subzone
  values = {
    zone_id = "ZSUBZONE00000000001"
  }
}

# aws_ram_resource_association valida resource_arn como ARN de verdade — validação de schema
# do provider, roda sob mock_provider (mesma família da checagem de tamanho do metadata SAML).
# Sem este override global, o id sintético que o mock atribui a aws_ec2_transit_gateway.hub
# não é um ARN válido, e todo run que não sobrescreve `arn` explicitamente falha por isso —
# não pelo que o run pretende testar.
override_resource {
  target = aws_ec2_transit_gateway.hub
  values = {
    arn = "arn:aws:ec2:us-east-1:000000000000:transit-gateway/tgw-0000000000000000f"
  }
}

# --------------------------------------------------------------------------------------
# Transit Gateway — o isolamento
# --------------------------------------------------------------------------------------

run "o_tgw_nasce_sem_association_e_sem_propagation_default" {
  command = plan

  # Estes dois são O passo. O default da AWS é "enable" nos dois, e com eles ligados todo
  # attachment aprende todo mundo — o isolamento por tenant fica impossível de construir
  # depois sem mexer em recurso já em uso.
  assert {
    condition     = aws_ec2_transit_gateway.hub.default_route_table_association == "disable"
    error_message = "default_route_table_association tem de ser disable, recebido ${aws_ec2_transit_gateway.hub.default_route_table_association}"
  }

  assert {
    condition     = aws_ec2_transit_gateway.hub.default_route_table_propagation == "disable"
    error_message = "default_route_table_propagation tem de ser disable, recebido ${aws_ec2_transit_gateway.hub.default_route_table_propagation}"
  }
}

# A route table do hub tem de pertencer AO TGW desta raiz. Comparar
# `route_table.transit_gateway_id` com `aws_ec2_transit_gateway.hub.id` sem override compara
# dois desconhecidos e passa sempre — a asserção vazia que esta base já produziu duas vezes.
#
# E um override só prova o VALOR, não a LIGAÇÃO: com o id fixo no código igual ao injetado, a
# asserção passaria sem fio. Daí dois runs com ids diferentes (lição do 1.3).

run "a_route_table_pertence_ao_tgw_desta_raiz" {
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
    condition     = aws_ec2_transit_gateway_route_table.hub.transit_gateway_id == "tgw-aaaaaaaaaaaaaaaa1"
    error_message = "a route table deveria apontar para o TGW desta raiz, recebido ${aws_ec2_transit_gateway_route_table.hub.transit_gateway_id}"
  }
}

run "e_acompanha_outro_tgw" {
  command = plan

  override_resource {
    target          = aws_ec2_transit_gateway.hub
    override_during = plan
    values = {
      id  = "tgw-bbbbbbbbbbbbbbbb2"
      arn = "arn:aws:ec2:us-east-1:000000000000:transit-gateway/tgw-bbbbbbbbbbbbbbbb2"
    }
  }

  assert {
    condition     = aws_ec2_transit_gateway_route_table.hub.transit_gateway_id == "tgw-bbbbbbbbbbbbbbbb2"
    error_message = "trocando o TGW, a route table deveria trocar junto — recebido ${aws_ec2_transit_gateway_route_table.hub.transit_gateway_id}"
  }
}

# --------------------------------------------------------------------------------------
# Certificado
# --------------------------------------------------------------------------------------

run "o_certificado_e_emitido_sob_a_subzona_delegada" {
  command = plan

  assert {
    condition     = aws_acm_certificate.vpn.domain_name == "vpn.us-east-1.nonprod.exemplo.com"
    error_message = "o certificado deveria ser emitido para vpn.<regiao>.<subzona>, recebido ${aws_acm_certificate.vpn.domain_name}"
  }

  # Negativa que importa: emitir para a subzona ou para o apex daria um certificado que
  # colide com o wildcard do cluster (fase 3) e com o apex, que nem é nosso.
  assert {
    condition     = aws_acm_certificate.vpn.domain_name != "nonprod.exemplo.com" && aws_acm_certificate.vpn.domain_name != "exemplo.com"
    error_message = "o certificado do endpoint não pode ser da subzona nem do apex"
  }

  assert {
    condition     = aws_acm_certificate.vpn.validation_method == "DNS"
    error_message = "validação por DNS é o que dispensa qualquer chave privada nossa, recebido ${aws_acm_certificate.vpn.validation_method}"
  }
}

# O registro de validação tem de cair na SUBZONA, não na pai. É a mesma armadilha que já custou
# tempo no ClusterIssuer do cert-manager: o desafio escrito na zona errada nunca é encontrado,
# porque quem é autoritativa é a subzona.
run "a_validacao_e_escrita_na_subzona_nao_na_pai" {
  command = plan

  assert {
    condition     = aws_route53_record.vpn_validation.zone_id == "ZSUBZONE00000000001"
    error_message = "o registro de validação deveria ir para a zona da subzona, recebido ${aws_route53_record.vpn_validation.zone_id}"
  }
}

run "e_acompanha_outra_zona" {
  command = plan

  override_data {
    target = data.aws_route53_zone.subzone
    values = {
      zone_id = "ZOUTRAZONA000000002"
    }
  }

  assert {
    condition     = aws_route53_record.vpn_validation.zone_id == "ZOUTRAZONA000000002"
    error_message = "trocando a zona lida, o registro de validação deveria trocar junto — recebido ${aws_route53_record.vpn_validation.zone_id}"
  }
}

# --------------------------------------------------------------------------------------
# Client VPN
# --------------------------------------------------------------------------------------

run "o_endpoint_autentica_por_saml_e_nao_por_certificado" {
  command = plan

  assert {
    condition     = one(aws_ec2_client_vpn_endpoint.hub.authentication_options).type == "federated-authentication"
    error_message = "a autenticação tem de ser federada — certificado mútuo custa a demo de conceder/revogar. Recebido ${one(aws_ec2_client_vpn_endpoint.hub.authentication_options).type}"
  }

  # Sem isto todo o tráfego da máquina do operador atravessaria a AWS.
  assert {
    condition     = aws_ec2_client_vpn_endpoint.hub.split_tunnel == true
    error_message = "split_tunnel tem de estar ligado"
  }

  # A alternativa que a doc do provider desaconselha para quem destrói a camada todo dia: o
  # attachment criado por transit_gateway_configuration leva horas para sair e prende o TGW.
  assert {
    condition     = length(aws_ec2_client_vpn_endpoint.hub.transit_gateway_configuration) == 0
    error_message = "o endpoint não pode usar transit_gateway_configuration — o attachment dele leva horas para deletar e impede destruir o TGW"
  }

  assert {
    condition     = aws_ec2_client_vpn_endpoint.hub.vpc_id == "vpc-hub000000000001"
    error_message = "o endpoint deveria nascer na VPC hub lida por tag, recebido ${aws_ec2_client_vpn_endpoint.hub.vpc_id}"
  }
}

run "o_endpoint_usa_o_provider_saml_desta_raiz" {
  command = plan

  override_resource {
    target          = aws_iam_saml_provider.client_vpn
    override_during = plan
    values = {
      arn = "arn:aws:iam::000000000000:saml-provider/primeiro"
    }
  }

  assert {
    condition     = one(aws_ec2_client_vpn_endpoint.hub.authentication_options).saml_provider_arn == "arn:aws:iam::000000000000:saml-provider/primeiro"
    error_message = "o endpoint deveria apontar para o provider SAML desta raiz, recebido ${one(aws_ec2_client_vpn_endpoint.hub.authentication_options).saml_provider_arn}"
  }
}

run "e_acompanha_outro_provider_saml" {
  command = plan

  override_resource {
    target          = aws_iam_saml_provider.client_vpn
    override_during = plan
    values = {
      arn = "arn:aws:iam::000000000000:saml-provider/segundo"
    }
  }

  assert {
    condition     = one(aws_ec2_client_vpn_endpoint.hub.authentication_options).saml_provider_arn == "arn:aws:iam::000000000000:saml-provider/segundo"
    error_message = "trocando o provider SAML, o endpoint deveria trocar junto — recebido ${one(aws_ec2_client_vpn_endpoint.hub.authentication_options).saml_provider_arn}"
  }
}

# O certificado que o endpoint consome vem do certificado desta raiz, e o valor se prova com
# dois overrides. O que NÃO se prova por valor é a ordenação: o endpoint referencia
# `aws_acm_certificate_validation.vpn.certificate_arn` justamente para nascer só depois de a
# validação concluir, mas esse ARN é o MESMO de `aws_acm_certificate.vpn.arn` — nenhuma
# asserção de valor distingue as duas referências.
#
# Escrito aqui em vez de mascarado numa asserção que passaria de qualquer jeito: a ordenação é
# aresta do grafo, e o `terraform test` não assere grafo. Ela se confere lendo o código, e o
# sintoma de tê-la errado aparece na conexão do operador (certificado
# PENDING_VALIDATION), não no apply.
#
# Overrides são no `aws_acm_certificate` porque `certificate_arn` do recurso de validação é
# ARGUMENTO, não atributo computado: sobrescrevê-lo não muda o que o plan propaga.

run "o_endpoint_consome_o_certificado_desta_raiz" {
  command = plan

  override_resource {
    target          = aws_acm_certificate.vpn
    override_during = plan
    values = {
      arn = "arn:aws:acm:us-east-1:000000000000:certificate/primeiro"

      # Obrigatório aqui, e não é redundância: `override_resource` substitui os atributos
      # computados POR INTEIRO. Omitir isto deixa `domain_validation_options` como set vazio,
      # e o índice em main.tf falha com "the collection has no elements" — erro que parece bug
      # do código e é artefato do override.
      domain_validation_options = [{
        domain_name           = "vpn.nonprod.exemplo.com"
        resource_record_name  = "_acme.vpn.nonprod.exemplo.com"
        resource_record_type  = "CNAME"
        resource_record_value = "primeiro.acm-validations.aws"
      }]
    }
  }

  assert {
    condition     = aws_ec2_client_vpn_endpoint.hub.server_certificate_arn == "arn:aws:acm:us-east-1:000000000000:certificate/primeiro"
    error_message = "o endpoint deveria consumir o certificado desta raiz, recebido ${aws_ec2_client_vpn_endpoint.hub.server_certificate_arn}"
  }

  assert {
    condition     = aws_acm_certificate_validation.vpn.certificate_arn == "arn:aws:acm:us-east-1:000000000000:certificate/primeiro"
    error_message = "a validação deveria ser do certificado desta raiz, recebido ${aws_acm_certificate_validation.vpn.certificate_arn}"
  }
}

run "e_acompanha_outro_certificado" {
  command = plan

  override_resource {
    target          = aws_acm_certificate.vpn
    override_during = plan
    values = {
      arn = "arn:aws:acm:us-east-1:000000000000:certificate/segundo"

      domain_validation_options = [{
        domain_name           = "vpn.nonprod.exemplo.com"
        resource_record_name  = "_acme.vpn.nonprod.exemplo.com"
        resource_record_type  = "CNAME"
        resource_record_value = "segundo.acm-validations.aws"
      }]
    }
  }

  assert {
    condition     = aws_ec2_client_vpn_endpoint.hub.server_certificate_arn == "arn:aws:acm:us-east-1:000000000000:certificate/segundo"
    error_message = "trocando o certificado, o endpoint deveria trocar junto — recebido ${aws_ec2_client_vpn_endpoint.hub.server_certificate_arn}"
  }
}

# --------------------------------------------------------------------------------------
# Associação e rota
# --------------------------------------------------------------------------------------

run "associa_uma_subnet_privada_do_hub_por_az" {
  command = plan

  assert {
    condition     = length(aws_ec2_client_vpn_network_association.hub) == 2
    error_message = "deveria haver uma associação por subnet privada do hub (2), há ${length(aws_ec2_client_vpn_network_association.hub)}"
  }

  assert {
    condition = toset([for association in aws_ec2_client_vpn_network_association.hub : association.subnet_id]) == toset([
      "subnet-priv0000000a", "subnet-priv0000000b"
    ])
    error_message = "as associações deveriam usar as subnets privadas lidas por tag, recebido ${jsonencode([for a in aws_ec2_client_vpn_network_association.hub : a.subnet_id])}"
  }
}

# Segundo conjunto, tamanho diferente: uma lista fixa de duas subnets no código passaria no run
# anterior e cairia aqui.
run "e_acompanha_outro_conjunto_de_subnets" {
  command = plan

  override_module {
    target = module.network

    outputs = {
      vpc_id                 = "vpc-hub000000000001"
      vpc_cidr               = "10.1.0.0/16"
      private_subnet_ids     = ["subnet-outra00001", "subnet-outra00002", "subnet-outra00003"]
      public_subnet_ids      = ["subnet-pub00000000a", "subnet-pub00000000b"]
      private_route_table_id = "rtb-hubprivate00001"
      public_route_table_id  = "rtb-hubpublic000001"
    }
  }

  assert {
    condition     = length(aws_ec2_client_vpn_network_association.hub) == 3
    error_message = "trocando as subnets lidas, as associações deveriam acompanhar — há ${length(aws_ec2_client_vpn_network_association.hub)}"
  }

  assert {
    condition = toset([for association in aws_ec2_client_vpn_network_association.hub : association.subnet_id]) == toset([
      "subnet-outra00001", "subnet-outra00002", "subnet-outra00003"
    ])
    error_message = "recebido ${jsonencode([for a in aws_ec2_client_vpn_network_association.hub : a.subnet_id])}"
  }
}

run "a_rota_e_do_supernet_inteiro_nao_da_vpc_hub" {
  command = plan

  # Rota é topologia: uma só, para toda a supernet. Se fosse o CIDR da VPC hub, nenhuma spoke
  # seria alcançável pelo túnel — e a AWS já acrescenta a local do hub sozinha na associação,
  # então essa rota não precisaria existir.
  assert {
    condition     = alltrue([for route in aws_ec2_client_vpn_route.supernet : route.destination_cidr_block == "10.0.0.0/12"])
    error_message = "a rota deveria ser do supernet 10.0.0.0/12, recebido ${jsonencode([for r in aws_ec2_client_vpn_route.supernet : r.destination_cidr_block])}"
  }

  # alltrue([]) é true — sem a contagem ao lado, a asserção acima passaria com zero rotas.
  assert {
    condition     = length(aws_ec2_client_vpn_route.supernet) == 2
    error_message = "deveria haver uma rota por subnet associada (2), há ${length(aws_ec2_client_vpn_route.supernet)}"
  }
}

# --------------------------------------------------------------------------------------
# Authorization rules — a política
# --------------------------------------------------------------------------------------

run "uma_authorization_rule_por_grupo_e_nunca_para_todos" {
  command = plan

  variables {
    operator_group_ids = [
      "11111111-2222-3333-4444-555555555555",
      "66666666-7777-8888-9999-aaaaaaaaaaaa",
    ]
  }

  assert {
    condition     = length(aws_ec2_client_vpn_authorization_rule.operators) == 2
    error_message = "deveria haver uma rule por grupo (2), há ${length(aws_ec2_client_vpn_authorization_rule.operators)}"
  }

  assert {
    condition = toset([for rule in aws_ec2_client_vpn_authorization_rule.operators : rule.access_group_id]) == toset([
      "11111111-2222-3333-4444-555555555555",
      "66666666-7777-8888-9999-aaaaaaaaaaaa",
    ])
    error_message = "as rules deveriam ser por grupo, recebido ${jsonencode([for r in aws_ec2_client_vpn_authorization_rule.operators : r.access_group_id])}"
  }

  # A que apaga metade do valor de ter escolhido SAML. Com authorize_all_groups, todo mundo que
  # autentica alcança o CIDR e "o Fulano só chega na spoke dele" deixa de existir — sem erro e
  # sem aviso, o que é o que a torna perigosa.
  assert {
    condition     = alltrue([for rule in aws_ec2_client_vpn_authorization_rule.operators : rule.authorize_all_groups != true])
    error_message = "nenhuma rule pode ter authorize_all_groups — perde-se o CIDR por grupo"
  }
}

run "sem_gerenciar_autorizacao_nenhuma_rule_e_criada" {
  command = plan

  variables {
    manage_authorization = false
    operator_group_ids   = []
  }

  assert {
    condition     = length(aws_ec2_client_vpn_authorization_rule.operators) == 0
    error_message = "com manage_authorization desligado não deveria haver rule"
  }

  # O interruptor desliga a POLÍTICA, não o caminho: endpoint e rota continuam de pé, e é isso
  # que permite exercitar o túnel antes de o grupo do 4.1 existir.
  assert {
    condition     = length(aws_ec2_client_vpn_route.supernet) == 2
    error_message = "as rotas deveriam continuar existindo sem authorization rule"
  }
}

# --------------------------------------------------------------------------------------
# Validações que falham fechado
# --------------------------------------------------------------------------------------

run "client_cidr_dentro_do_supernet_e_erro" {
  command = plan

  variables {
    # Colidiria com a spoke N=8. A faixa não pode ser trocada depois de o endpoint existir,
    # então errar aqui custa recriar o endpoint.
    client_cidr_block = "10.8.0.0/22"
  }

  expect_failures = [var.client_cidr_block]
}

run "client_cidr_pequeno_demais_e_erro" {
  command = plan

  variables {
    client_cidr_block = "100.64.0.0/23"
  }

  expect_failures = [var.client_cidr_block]
}

run "client_cidr_sem_prefixo_e_erro" {
  command = plan

  variables {
    client_cidr_block = "100.64.0.0"
  }

  expect_failures = [var.client_cidr_block]
}

# Nome de grupo em vez de id é o erro que dá túnel que sobe e não alcança nada, com mensagem
# que não ajuda. Falhar no plan é muito mais barato.
run "nome_de_grupo_no_lugar_do_id_e_erro" {
  command = plan

  variables {
    operator_group_ids = ["platform-admins"]
  }

  expect_failures = [var.operator_group_ids]
}

run "lista_de_grupos_vazia_com_autorizacao_ligada_e_erro" {
  command = plan

  variables {
    operator_group_ids = []
  }

  expect_failures = [var.operator_group_ids]
}

run "dominio_com_ponto_final_e_erro" {
  command = plan

  variables {
    base_domain = "exemplo.com."
  }

  expect_failures = [var.base_domain]
}
