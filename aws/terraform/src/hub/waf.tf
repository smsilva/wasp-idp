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
