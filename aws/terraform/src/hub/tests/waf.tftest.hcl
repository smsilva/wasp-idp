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

# --------------------------------------------------------------------------------------
# Managed rule groups
# --------------------------------------------------------------------------------------

# ATENCAO: sob mock_provider o data source devolve `rules = []` (verificado em spike). Sem o
# override_data abaixo, o dynamic gera ZERO overrides e qualquer assercao sobre eles passa verde
# e vazia — a armadilha `alltrue([])` que este repo ja catalogou. O override injeta uma lista
# conhecida; e ela que da conteudo a assercao.
run "o_common_rule_set_nasce_inteiro_em_count" {
  command = plan

  override_data {
    target = data.aws_wafv2_managed_rule_group.common

    values = {
      rules = [
        { name = "SizeRestrictions_BODY" },
        { name = "CrossSiteScripting_BODY" },
        { name = "GenericLFI_URIPATH" },
      ]
    }
  }

  assert {
    condition = one([
      for r in aws_wafv2_web_acl.hub.rule : r.statement[0].managed_rule_group_statement[0].name
      if r.name == "aws-common-rule-set"
    ]) == "AWSManagedRulesCommonRuleSet"
    error_message = "o grupo tem de ser o AWSManagedRulesCommonRuleSet"
  }

  assert {
    condition = one([
      for r in aws_wafv2_web_acl.hub.rule : r.statement[0].managed_rule_group_statement[0].vendor_name
      if r.name == "aws-common-rule-set"
    ]) == "AWS"
    error_message = "vendor_name tem de ser AWS"
  }

  # Uma entrada de override por regra do grupo — o mecanismo que a AWS recomenda para observar,
  # porque da metrica e label POR REGRA. O override_action no grupo inteiro daria um contador so
  # e nao diria QUAL regra casou, que e justamente a informacao que decide a promocao.
  assert {
    condition = length(one([
      for r in aws_wafv2_web_acl.hub.rule : r.statement[0].managed_rule_group_statement[0].rule_action_override
      if r.name == "aws-common-rule-set"
    ])) == 3
    error_message = "esperado um rule_action_override por regra do grupo (3 na lista injetada)"
  }

  assert {
    condition = alltrue([
      for o in one([
        for r in aws_wafv2_web_acl.hub.rule : r.statement[0].managed_rule_group_statement[0].rule_action_override
        if r.name == "aws-common-rule-set"
      ]) : length(o.action_to_use[0].count) == 1
    ])
    error_message = "todo override tem de usar a acao count"
  }

  # Os nomes vem do data source, nao de uma lista colada no codigo.
  assert {
    condition = toset([
      for o in one([
        for r in aws_wafv2_web_acl.hub.rule : r.statement[0].managed_rule_group_statement[0].rule_action_override
        if r.name == "aws-common-rule-set"
      ]) : o.name
    ]) == toset(["SizeRestrictions_BODY", "CrossSiteScripting_BODY", "GenericLFI_URIPATH"])
    error_message = "os nomes dos overrides nao vieram do data source"
  }
}

# Segundo override_data com TAMANHO diferente: um override prova o valor, dois provam a ligacao.
# Nenhuma lista fixa no codigo satisfaz os dois runs.
run "os_overrides_acompanham_o_data_source" {
  command = plan

  override_data {
    target = data.aws_wafv2_managed_rule_group.common

    values = {
      rules = [
        { name = "NoUserAgent_HEADER" },
        { name = "UserAgent_BadBots_HEADER" },
      ]
    }
  }

  assert {
    condition = toset([
      for o in one([
        for r in aws_wafv2_web_acl.hub.rule : r.statement[0].managed_rule_group_statement[0].rule_action_override
        if r.name == "aws-common-rule-set"
      ]) : o.name
    ]) == toset(["NoUserAgent_HEADER", "UserAgent_BadBots_HEADER"])
    error_message = "a lista de overrides esta fixa no codigo em vez de vir do data source"
  }
}

# A promocao: com block, a lista de overrides ZERA e cada regra do grupo volta a aplicar a acao
# nativa dela. E este o mecanismo da promocao — nao ha nada mais a mudar.
run "promover_para_block_zera_os_overrides" {
  command = plan

  variables {
    waf_managed_rules_action = "block"
  }

  override_data {
    target = data.aws_wafv2_managed_rule_group.common

    values = {
      rules = [
        { name = "SizeRestrictions_BODY" },
        { name = "CrossSiteScripting_BODY" },
        { name = "GenericLFI_URIPATH" },
      ]
    }
  }

  assert {
    condition = length(one([
      for r in aws_wafv2_web_acl.hub.rule : r.statement[0].managed_rule_group_statement[0].rule_action_override
      if r.name == "aws-common-rule-set"
    ])) == 0
    error_message = "com waf_managed_rules_action=block nenhum override pode sobrar"
  }

  # O override_action fica `none` nas duas posturas: quem faz o Count e o rule_action_override
  # por regra, nao o override do grupo inteiro (que a AWS desaconselha para este fim).
  assert {
    condition = length(one([
      for r in aws_wafv2_web_acl.hub.rule : r.override_action[0].none
      if r.name == "aws-common-rule-set"
    ])) == 1
    error_message = "o override_action do grupo e sempre none — o Count vem dos rule_action_override"
  }
}

# A ordem e a decisao de maior impacto num Web ACL, porque acao terminante para a avaliacao. Em
# Count nada termina, entao esta assercao protege uma propriedade que ainda nao importa — e passa
# a importar exatamente no dia da promocao, quando ninguem vai lembrar de conferir.
#
# A ordem segue a tabela recomendada pela AWS: rate-based antes de tudo ("stop volumetric abuse
# early before it consumes capacity in more expensive downstream rules"), depois IP reputation,
# depois os baseline, e por fim o use-case.
run "a_ordem_das_regras_segue_a_recomendacao_da_aws" {
  command = plan

  assert {
    condition = one([for r in aws_wafv2_web_acl.hub.rule : r.priority if r.name == "rate-limit"]) < one([
      for r in aws_wafv2_web_acl.hub.rule : r.priority if r.name == "aws-ip-reputation"
    ])
    error_message = "a rate rule tem de ser avaliada antes dos managed rule groups"
  }

  assert {
    condition = one([for r in aws_wafv2_web_acl.hub.rule : r.priority if r.name == "aws-ip-reputation"]) < one([
      for r in aws_wafv2_web_acl.hub.rule : r.priority if r.name == "aws-common-rule-set"
    ])
    error_message = "IP reputation e avaliacao barata: vem antes da inspecao de conteudo"
  }

  assert {
    condition = one([for r in aws_wafv2_web_acl.hub.rule : r.priority if r.name == "aws-common-rule-set"]) < one([
      for r in aws_wafv2_web_acl.hub.rule : r.priority if r.name == "aws-known-bad-inputs"
    ])
    error_message = "os dois baseline sao avaliados em ordem: CRS antes de KnownBadInputs"
  }

  assert {
    condition = one([for r in aws_wafv2_web_acl.hub.rule : r.priority if r.name == "aws-known-bad-inputs"]) < one([
      for r in aws_wafv2_web_acl.hub.rule : r.priority if r.name == "aws-sqli"
    ])
    error_message = "os baseline (CRS, KnownBadInputs) vem antes do use-case (SQLi)"
  }

  # Prioridade duplicada e recusada pelo servico com uma mensagem que nao diz qual par colidiu.
  assert {
    condition     = length(toset([for r in aws_wafv2_web_acl.hub.rule : r.priority])) == length(aws_wafv2_web_acl.hub.rule)
    error_message = "ha prioridade duplicada entre as regras do Web ACL"
  }

  # Os quatro grupos presentes, com o nome certo do servico.
  assert {
    condition = toset(flatten([
      for r in aws_wafv2_web_acl.hub.rule : [
        for s in r.statement[0].managed_rule_group_statement : s.name
      ]
      ])) == toset([
      "AWSManagedRulesAmazonIpReputationList",
      "AWSManagedRulesCommonRuleSet",
      "AWSManagedRulesKnownBadInputsRuleSet",
      "AWSManagedRulesSQLiRuleSet",
    ])
    error_message = "os quatro managed rule groups do desenho nao estao todos presentes"
  }
}
