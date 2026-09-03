# WAF do hub — o Web ACL na frente do ALB publico.
#
# A postura e Count em TODAS as regras: o guia prescritivo da AWS aponta Block como estado-alvo
# de producao, mas pressupoe trafego real para tunar contra, que este ALB ainda nao tem. A
# promocao e troca de parametro, e o criterio esta na spec.

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

override_resource {
  target = aws_ec2_transit_gateway.hub
  values = {
    arn = "arn:aws:ec2:us-east-1:000000000000:transit-gateway/tgw-0000000000000000f"
  }
}

# --------------------------------------------------------------------------------------
# O Web ACL
# --------------------------------------------------------------------------------------

run "o_web_acl_e_regional_e_deixa_passar_o_que_nao_casa_regra" {
  command = plan

  # REGIONAL, nao CLOUDFRONT: o alvo e um ALB. Errar isto cria um Web ACL que nunca associa,
  # e a mensagem de erro fala de ARN, nao de scope.
  assert {
    condition     = aws_wafv2_web_acl.hub.scope == "REGIONAL"
    error_message = "o Web ACL de um ALB e REGIONAL, veio ${aws_wafv2_web_acl.hub.scope}"
  }

  # Fail-OPEN de proposito: request que nao casa nenhuma regra passa. Um default_action de block
  # aqui derrubaria o site inteiro — o WAF filtra o que reconhece, nao autoriza o que conhece.
  assert {
    condition     = length(aws_wafv2_web_acl.hub.default_action[0].allow) == 1
    error_message = "o default_action tem de ser allow: fail-closed derrubaria todo o trafego legitimo"
  }

  # sampled_requests e a UNICA observabilidade que existe antes de a #86 (logging) ser aplicada.
  # Sem ela nao ha como decidir a promocao de Count para Block.
  assert {
    condition     = aws_wafv2_web_acl.hub.visibility_config[0].sampled_requests_enabled
    error_message = "sem sampled_requests nao ha como tunar a postura antes da #86"
  }
}

# --------------------------------------------------------------------------------------
# A rate-based rule
# --------------------------------------------------------------------------------------

run "a_rate_rule_conta_por_ip_na_janela_de_300s" {
  command = plan

  assert {
    condition = one([
      for r in aws_wafv2_web_acl.hub.rule : r.statement[0].rate_based_statement[0].limit
      if r.name == "rate-limit"
    ]) == 2000
    error_message = "o limite default e 2000 requests por IP"
  }

  assert {
    condition = one([
      for r in aws_wafv2_web_acl.hub.rule : r.statement[0].rate_based_statement[0].aggregate_key_type
      if r.name == "rate-limit"
    ]) == "IP"
    error_message = "a agregacao e por IP de origem"
  }

  # A janela NAO e fixa: 60/120/300/600 sao os valores validos e 300 e o default. Explicita no
  # codigo para nao parecer acidental.
  assert {
    condition = one([
      for r in aws_wafv2_web_acl.hub.rule : r.statement[0].rate_based_statement[0].evaluation_window_sec
      if r.name == "rate-limit"
    ]) == 300
    error_message = "a janela de avaliacao e 300s"
  }

  # Count por default. A rate rule e a que menos produz falso positivo e a unica que mitiga DoS
  # L7 — sera provavelmente a primeira a ser promovida, e por isso tem variavel propria.
  assert {
    condition = length(one([
      for r in aws_wafv2_web_acl.hub.rule : r.action[0].count
      if r.name == "rate-limit"
    ])) == 1
    error_message = "a postura default da rate rule e count"
  }
}

# Mutacao real: a variavel troca a acao de count para block. Sem este run, uma implementacao com
# `count {}` fixo no codigo passaria verde.
run "a_rate_rule_bloqueia_quando_promovida" {
  command = plan

  variables {
    waf_rate_limit_action = "block"
  }

  assert {
    condition = length(one([
      for r in aws_wafv2_web_acl.hub.rule : r.action[0].block
      if r.name == "rate-limit"
    ])) == 1
    error_message = "com waf_rate_limit_action=block a acao tem de ser block"
  }

  assert {
    condition = length(one([
      for r in aws_wafv2_web_acl.hub.rule : r.action[0].count
      if r.name == "rate-limit"
    ])) == 0
    error_message = "promovida a block, a rate rule nao pode continuar em count"
  }
}

run "o_limite_da_rate_rule_e_parametrizavel" {
  command = plan

  variables {
    waf_rate_limit = 500
  }

  assert {
    condition = one([
      for r in aws_wafv2_web_acl.hub.rule : r.statement[0].rate_based_statement[0].limit
      if r.name == "rate-limit"
    ]) == 500
    error_message = "o limite tem de vir da variavel, nao estar fixo no codigo"
  }
}

# --------------------------------------------------------------------------------------
# A associacao — o coracao da issue
# --------------------------------------------------------------------------------------

# Sem associacao o Web ACL existe, cobra os mesmos US$ 10/mes e NAO protege nada. Como os dois
# lados (arn do ALB e arn do Web ACL) sao computed, a assercao so existe com override_resource.
#
# O override substitui os computados POR INTEIRO: precisa injetar dns_name e zone_id junto do
# arn, porque os tres tem consumidores em outputs.tf (linhas 38, 48 e 53). Omitir um quebra o
# plan por artefato de teste, e o erro aponta para o lugar errado.
run "o_web_acl_esta_associado_ao_alb_do_hub" {
  command = plan

  override_resource {
    target          = aws_lb.hub
    override_during = plan

    values = {
      arn      = "arn:aws:elasticloadbalancing:us-east-1:000000000000:loadbalancer/app/hub-a/aaaaaaaaaaaaaaaa"
      dns_name = "hub-a-000000000.us-east-1.elb.amazonaws.com"
      zone_id  = "Z35SXDOTRQ7X7K"
    }
  }

  assert {
    condition     = aws_wafv2_web_acl_association.hub.resource_arn == "arn:aws:elasticloadbalancing:us-east-1:000000000000:loadbalancer/app/hub-a/aaaaaaaaaaaaaaaa"
    error_message = "a associacao tem de apontar para o ALB do hub, veio ${aws_wafv2_web_acl_association.hub.resource_arn}"
  }
}

# Segundo run com ARN diferente: UM override prova o VALOR, dois provam a LIGACAO. Com um so,
# um arn colado a mao no codigo igual ao injetado passaria verde.
run "a_associacao_acompanha_o_alb_e_nao_um_arn_fixo" {
  command = plan

  override_resource {
    target          = aws_lb.hub
    override_during = plan

    values = {
      arn      = "arn:aws:elasticloadbalancing:us-east-1:000000000000:loadbalancer/app/hub-b/bbbbbbbbbbbbbbbb"
      dns_name = "hub-b-111111111.us-east-1.elb.amazonaws.com"
      zone_id  = "Z35SXDOTRQ7X7K"
    }
  }

  assert {
    condition     = aws_wafv2_web_acl_association.hub.resource_arn == "arn:aws:elasticloadbalancing:us-east-1:000000000000:loadbalancer/app/hub-b/bbbbbbbbbbbbbbbb"
    error_message = "o arn da associacao esta fixo no codigo em vez de vir do ALB"
  }
}
