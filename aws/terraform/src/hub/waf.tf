# --------------------------------------------------------------------------------------
# WAF — inspecao de camada 7 na frente do ALB publico
# --------------------------------------------------------------------------------------
#
# O ALB do hub e o unico ponto de entrada publico do desenho, e ate aqui nada olhava o CONTEUDO
# das requests: o security group decide por porta e origem, o listener decide por host. O Web ACL
# e a camada que falta.
#
# Postura: TODAS as regras em Count. Nao e timidez — e o que a doc da AWS manda fazer antes de
# bloquear ("test and tune the rules in count mode with your production traffic before enabling
# them"), e este ALB ainda nao tem trafego de producao para tunar contra. A promocao para Block e
# troca de variavel, e o criterio esta escrito na spec.

# Os nomes das regras de cada grupo vem do proprio servico, nao de uma lista mantida a mao.
#
# Sao 46 regras nos quatro grupos, e uma lista fixa envelheceria em SILENCIO: quando a AWS
# acrescentasse uma regra nova ao grupo, ela nasceria BLOQUEANDO sem ninguem ter decidido isso —
# exatamente o modo de falha que a postura Count existe para evitar. O preco e que o plan passa a
# chamar DescribeManagedRuleGroup (precisa de wafv2:DescribeManagedRuleGroup na role que planeja).
#
# O acoplamento tem prazo: com waf_managed_rules_action = "block" a lista de overrides zera e os
# data sources deixam de influenciar o resultado.
data "aws_wafv2_managed_rule_group" "common" {
  name        = "AWSManagedRulesCommonRuleSet"
  vendor_name = "AWS"
  scope       = "REGIONAL"
}

data "aws_wafv2_managed_rule_group" "ip_reputation" {
  name        = "AWSManagedRulesAmazonIpReputationList"
  vendor_name = "AWS"
  scope       = "REGIONAL"
}

data "aws_wafv2_managed_rule_group" "known_bad_inputs" {
  name        = "AWSManagedRulesKnownBadInputsRuleSet"
  vendor_name = "AWS"
  scope       = "REGIONAL"
}

data "aws_wafv2_managed_rule_group" "sqli" {
  name        = "AWSManagedRulesSQLiRuleSet"
  vendor_name = "AWS"
  scope       = "REGIONAL"
}

resource "aws_wafv2_web_acl" "hub" {
  name  = "${var.name}-ingress-waf"
  scope = "REGIONAL"

  # WAFv2 REGIONAL e por regiao, ao contrario do aws_iam_saml_provider (IAM e global) e do FQDN
  # da VPN (a subzona e uma so) — os dois casos que obrigaram var.region a entrar nos nomes deste
  # modulo. Aqui o nome NAO precisa da regiao, e acrescenta-la so criaria ruido.

  # Fail-OPEN: request que nao casa nenhuma regra passa. O WAF filtra o que reconhece como
  # malicioso; ele nao e uma allowlist. default_action = block derrubaria o site inteiro.
  default_action {
    allow {}
  }

  # A rate-based rule vem ANTES dos managed rule groups (priority 50 contra 70-90), seguindo a
  # ordem recomendada pela AWS: "block the most traffic, at the lowest cost, as early as
  # possible". Em Count nada termina a avaliacao, entao a ordem e inocua hoje — e decisiva no dia
  # em que a postura virar Block.
  rule {
    name     = "rate-limit"
    priority = 50

    action {
      dynamic "count" {
        for_each = var.waf_rate_limit_action == "count" ? [1] : []

        content {}
      }

      dynamic "block" {
        for_each = var.waf_rate_limit_action == "block" ? [1] : []

        content {}
      }
    }

    statement {
      rate_based_statement {
        limit              = var.waf_rate_limit
        aggregate_key_type = "IP"

        # 60/120/300/600 sao os valores validos; 300 e o default do servico. Explicito para
        # deixar claro que e escolha, nao omissao.
        evaluation_window_sec = 300
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name}-rate-limit"
      sampled_requests_enabled   = true
    }
  }

  # Origens sabidamente maliciosas ou ofuscadas. Avaliacao barata, e por isso vem antes da
  # inspecao de conteudo: derruba volume que nao precisa chegar aos grupos caros.
  rule {
    name     = "aws-ip-reputation"
    priority = 70

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesAmazonIpReputationList"
        vendor_name = "AWS"

        dynamic "rule_action_override" {
          for_each = var.waf_managed_rules_action == "count" ? toset([
            for managed_rule in data.aws_wafv2_managed_rule_group.ip_reputation.rules : managed_rule.name
          ]) : toset([])

          content {
            name = rule_action_override.value

            action_to_use {
              count {}
            }
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name}-ip-reputation"
      sampled_requests_enabled   = true
    }
  }

  # Core Rule Set — a cobertura mais ampla (XSS, LFI, RFI, anomalias) e, segundo a propria AWS,
  # "the rule group most likely to produce false positives". As suspeitas de sempre estao
  # nomeadas na spec: SizeRestrictions_BODY (corta body > 8 KB) e CrossSiteScripting_BODY
  # (dispara em .docx/.xml/.svg).
  rule {
    name     = "aws-common-rule-set"
    priority = 80

    # SEMPRE none. Quem observa e o rule_action_override por regra, abaixo: a doc da AWS diz que
    # o override do grupo inteiro "is not a good option for testing the rules in a rule group",
    # porque devolve um contador so e esconde QUAL regra casou.
    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"

        # `version` fica sem fixar de proposito: a AWS atualiza o grupo com protecoes novas, e em
        # postura Count uma regra nova entra contando, sem bloquear nada por surpresa. Fixar
        # traria previsibilidade e a armadilha de rotacao — mesma familia do thumbprint do OIDC.

        dynamic "rule_action_override" {
          for_each = var.waf_managed_rules_action == "count" ? toset([
            for managed_rule in data.aws_wafv2_managed_rule_group.common.rules : managed_rule.name
          ]) : toset([])

          content {
            name = rule_action_override.value

            action_to_use {
              count {}
            }
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name}-common-rule-set"
      sampled_requests_enabled   = true
    }
  }

  # Exploits conhecidos (Log4j, desserializacao Java, path traversal). Segundo a AWS, "frequently
  # has a low false positive rate and low WCU cost, making it a good candidate to enforce early in
  # a deployment" — sera provavelmente o primeiro grupo a ser promovido a block.
  rule {
    name     = "aws-known-bad-inputs"
    priority = 81

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
        vendor_name = "AWS"

        dynamic "rule_action_override" {
          for_each = var.waf_managed_rules_action == "count" ? toset([
            for managed_rule in data.aws_wafv2_managed_rule_group.known_bad_inputs.rules : managed_rule.name
          ]) : toset([])

          content {
            name = rule_action_override.value

            action_to_use {
              count {}
            }
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name}-known-bad-inputs"
      sampled_requests_enabled   = true
    }
  }

  # Use-case, nao baseline: so se paga se houver SQL atras do ALB. Fica porque a #83 o pediu
  # explicitamente e os 200 WCU cabem no tier basico — mas e o primeiro candidato a sair se a
  # capacidade apertar (a #89 pode querer regras por tenant).
  rule {
    name     = "aws-sqli"
    priority = 90

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesSQLiRuleSet"
        vendor_name = "AWS"

        dynamic "rule_action_override" {
          for_each = var.waf_managed_rules_action == "count" ? toset([
            for managed_rule in data.aws_wafv2_managed_rule_group.sqli.rules : managed_rule.name
          ]) : toset([])

          content {
            name = rule_action_override.value

            action_to_use {
              count {}
            }
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name}-sqli"
      sampled_requests_enabled   = true
    }
  }

  # Obrigatorio, e nao e burocracia: sampled_requests e a unica janela para o que o WAF esta
  # contando enquanto o logging (#86) nao existe — e e dela que sai a decisao de promover.
  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.name}-ingress-waf"
    sampled_requests_enabled   = true
  }

  tags = merge(local.tags, { Name = "${var.name}-ingress-waf" })
}

# Sem esta associacao o Web ACL existe, cobra o mesmo e nao protege coisa nenhuma.
#
# NAO acrescentar time_sleep nem timeouts aqui: a doc da AWS avisa que um Web ACL recem-criado
# pode recusar a associacao enquanto propaga, mas o provider ja faz retry nessa excecao exata
# (WAFUnavailableEntityException) por 10 minutos — verificado no codigo do provider 6.62.0,
# web_acl_association.go linhas 44 e 83. Se um apply real falhar aqui, a alavanca e
# `timeouts { create }`, que e argumento nativo do recurso.
resource "aws_wafv2_web_acl_association" "hub" {
  resource_arn = aws_lb.hub.arn
  web_acl_arn  = aws_wafv2_web_acl.hub.arn
}
