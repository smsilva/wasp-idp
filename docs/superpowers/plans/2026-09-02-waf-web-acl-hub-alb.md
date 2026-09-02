# WAF Web ACL on the Hub ALB — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pôr um AWS WAF Web ACL regional na frente do ALB público do hub, com quatro managed rule groups da AWS e uma rate-based rule, todos em postura de observação (`Count`).

**Architecture:** Um arquivo novo `waf.tf` no módulo `aws/terraform/src/hub/` (o `main.tf` já tem 394 linhas; o Terraform funde todos os `.tf` do diretório). Um `aws_wafv2_web_acl` com cinco regras e um `aws_wafv2_web_acl_association` ligando ao `aws_lb.hub` que já existe. A postura de bloqueio é controlada por duas variáveis; a observação é feita por `rule_action_override` gerado a partir de data sources, não por `override_action` no grupo inteiro.

**Tech Stack:** Terraform, provider `hashicorp/aws ~> 6.0` (lock em 6.62.0), `terraform test` com `mock_provider`.

**Spec:** `docs/superpowers/specs/2026-09-02-waf-web-acl-hub-alb-design.md`

## Global Constraints

- **Idioma:** código, comentários e mensagens de commit em inglês seria o padrão do repo para *scripts*; **este módulo tem comentários em português sem acentuação** (ver `main.tf`). Seguir o que está no arquivo vizinho: comentários em pt-BR **sem acentos**, explicando o *porquê*, não o *quê*.
- **Provider:** `aws` 6.62.0 (lockfile). Todo fato de schema deste plano foi verificado nessa versão.
- **`rule` do `aws_wafv2_web_acl` é um SET** — acesso por índice não compila. Em asserção, extrair por nome: `one([for r in aws_wafv2_web_acl.hub.rule : r if r.name == "..."])`. Os blocos internos (`action`, `override_action`, `statement`, `visibility_config`) são LIST e aceitam `[0]`.
- **`visibility_config` é obrigatório** no topo do Web ACL **e dentro de cada `rule`**, com os três atributos: `cloudwatch_metrics_enabled`, `metric_name`, `sampled_requests_enabled`.
- **Sob `mock_provider`, `data.aws_wafv2_managed_rule_group.*.rules` devolve `[]`** (verificado em spike). Toda asserção sobre `rule_action_override` exige `override_data` explícito, senão passa vazia.
- **Prioridades:** rate-based `50`, IpReputation `70`, CommonRuleSet `80`, KnownBadInputs `81`, SQLi `90`.
- **Nenhuma mitigação de propagação no primeiro apply** — o provider já faz retry em `WAFUnavailableEntityException` por 10 min. Não acrescentar `time_sleep` nem `timeouts`.
- **Rodar `terraform test` com `-no-color`** (códigos ANSI quebram grep) e com `-filter` para não rodar a regressão inteira (>2 min) a cada ciclo.

---

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `aws/terraform/src/hub/waf.tf` (criar) | Web ACL, as cinco regras, os quatro data sources de managed rule group, a associação ao ALB |
| `aws/terraform/src/hub/variables.tf` (modificar, acrescentar ao fim) | `waf_managed_rules_action`, `waf_rate_limit_action`, `waf_rate_limit` |
| `aws/terraform/src/hub/tests/waf.tftest.hcl` (criar) | Toda a cobertura offline do WAF |
| `aws/docs/network/06-security.md` (modificar) | O WAF como camada L7 no diagrama de defesa em profundidade |

---

## Task 1: Web ACL com a rate-based rule e a associação ao ALB

Fatia fina de ponta a ponta: um Web ACL que existe, protege (contando) e está **associado** ao ALB. Os managed rule groups entram nas tasks 2 e 3.

**Files:**
- Create: `aws/terraform/src/hub/waf.tf`
- Modify: `aws/terraform/src/hub/variables.tf` (acrescentar ao fim)
- Test: `aws/terraform/src/hub/tests/waf.tftest.hcl`

**Interfaces:**
- Consumes: `aws_lb.hub.arn` (`main.tf:313`), `local.tags` (`main.tf:10`), `var.name`
- Produces: `aws_wafv2_web_acl.hub` (as tasks 2 e 3 acrescentam blocos `rule` a este recurso); as três variáveis

- [ ] **Step 1: Escrever o teste que falha**

Criar `aws/terraform/src/hub/tests/waf.tftest.hcl`. O preâmbulo (variáveis e os três overrides) é copiado de `tests/ingress-alb.tftest.hcl` — sob `command = plan` a configuração inteira é avaliada, então o módulo precisa planejar por completo mesmo para uma asserção que só toca o WAF.

```hcl
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
    target = aws_lb.hub

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
    target = aws_lb.hub

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
```

- [ ] **Step 2: Rodar o teste e confirmar que falha pelo motivo certo**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/src/hub
terraform test -no-color -filter=tests/waf.tftest.hcl 2>&1 | tail -20
```

Esperado: falha com `Reference to undeclared resource` para `aws_wafv2_web_acl.hub` — o recurso ainda não existe. **Se falhar com outra coisa** (erro de sintaxe no teste, variável faltando), corrigir o teste antes de seguir: um teste que falha pelo motivo errado não é um teste vermelho, é um teste quebrado.

- [ ] **Step 3: Acrescentar as três variáveis**

Ao fim de `aws/terraform/src/hub/variables.tf`:

```hcl
variable "waf_managed_rules_action" {
  description = <<-EOT
    Postura dos managed rule groups do WAF: `count` observa e deixa passar, `block` deixa cada
    grupo aplicar a acao nativa das suas regras.

    Nasce em `count` porque o guia prescritivo da AWS manda tunar com trafego de producao antes
    de bloquear, e este ALB ainda nao tem esse trafego. `block` e o estado-alvo — o criterio de
    promocao esta em docs/superpowers/specs/2026-09-02-waf-web-acl-hub-alb-design.md.
  EOT
  type        = string
  default     = "count"

  validation {
    condition     = contains(["count", "block"], var.waf_managed_rules_action)
    error_message = "waf_managed_rules_action tem de ser count ou block, recebido ${var.waf_managed_rules_action}."
  }
}

variable "waf_rate_limit_action" {
  description = <<-EOT
    Postura da rate-based rule, SEPARADA da dos managed rule groups de proposito: e a regra de
    falso positivo mais previsivel e a unica que mitiga DoS de camada 7, entao sera provavelmente
    a primeira a ser promovida a block. Uma variavel so forcaria promover tudo junto.
  EOT
  type        = string
  default     = "count"

  validation {
    condition     = contains(["count", "block"], var.waf_rate_limit_action)
    error_message = "waf_rate_limit_action tem de ser count ou block, recebido ${var.waf_rate_limit_action}."
  }
}

variable "waf_rate_limit" {
  description = "Requests por IP de origem na janela de 300s antes de a rate-based rule agir. O piso que a AWS aceita e 10."
  type        = number
  default     = 2000

  validation {
    condition     = var.waf_rate_limit >= 10
    error_message = "waf_rate_limit tem de ser no minimo 10 (piso da AWS), recebido ${var.waf_rate_limit}."
  }
}
```

- [ ] **Step 4: Criar o `waf.tf` com o Web ACL, a rate rule e a associação**

```hcl
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
```

- [ ] **Step 5: Rodar o teste e confirmar que passa**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/src/hub
terraform test -no-color -filter=tests/waf.tftest.hcl 2>&1 | tail -20
```

Esperado: `Success!` — nenhum run falhando.

Se algum run falhar com `Cannot index a set value`, a asserção está indexando `rule` diretamente — voltar ao padrão `one([for r in ... : ... if r.name == "..."])`.

- [ ] **Step 6: Provar que o teste da associação não é vazio (teste de mutação)**

O repo já teve duas asserções que passavam vazias. Provar que esta não é uma delas:

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/src/hub
sed -i 's/^  resource_arn = aws_lb.hub.arn$/  resource_arn = "arn:aws:elasticloadbalancing:us-east-1:000000000000:loadbalancer\/app\/hub-a\/aaaaaaaaaaaaaaaa"/' waf.tf
grep -n "resource_arn" waf.tf
terraform test -no-color -filter=tests/waf.tftest.hcl 2>&1 | tail -12
```

Esperado: o run `o_web_acl_esta_associado_ao_alb_do_hub` **passa** (o valor colado é igual ao injetado) e `a_associacao_acompanha_o_alb_e_nao_um_arn_fixo` **falha** — que é exatamente a prova de que o segundo run existe. Confirmar pelo `grep` que a mutação foi de fato aplicada antes de concluir qualquer coisa: um `sed` que não casa nada deixa o teste verde e é indistinguível de teste fraco.

Reverter:

```bash
git checkout waf.tf && grep -n "resource_arn" waf.tf
terraform test -no-color -filter=tests/waf.tftest.hcl 2>&1 | tail -5
```

Esperado: volta a `Success!`, nenhum run falhando.

- [ ] **Step 7: Commit**

```bash
cd /home/silvios/git/wasp-idp
git add aws/terraform/src/hub/waf.tf aws/terraform/src/hub/variables.tf aws/terraform/src/hub/tests/waf.tftest.hcl
git commit -m "$(cat <<'EOF'
feat(#84): Web ACL do hub com rate-based rule, associado ao ALB

Fatia fina de ponta a ponta: o Web ACL existe, conta e esta ASSOCIADO —
sem a associacao ele cobraria o mesmo e nao protegeria nada.

Postura Count por default nas duas variaveis; block e troca de parametro.
A rate rule tem variavel propria porque e a de falso positivo mais
previsivel e a unica que mitiga DoS L7 — sera a primeira a ser promovida.

A associacao e coberta por dois runs com ARNs diferentes: um override
prova o valor, dois provam a ligacao. Confirmado por mutacao.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01EybnMkQ3zJpCehCEijs392
EOF
)"
```

---

## Task 2: O primeiro managed rule group, com o mecanismo de `Count` por regra

Estabelece o padrão que a Task 3 replica: data source + `dynamic "rule_action_override"`. É a task onde a armadilha do mock aparece, e por isso ela vem sozinha.

**Files:**
- Modify: `aws/terraform/src/hub/waf.tf`
- Test: `aws/terraform/src/hub/tests/waf.tftest.hcl` (acrescentar runs ao fim)

**Interfaces:**
- Consumes: `aws_wafv2_web_acl.hub` e `var.waf_managed_rules_action` (Task 1)
- Produces: `data.aws_wafv2_managed_rule_group.common`; o padrão de bloco `rule` que a Task 3 repete quatro vezes

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar ao fim de `tests/waf.tftest.hcl`:

```hcl
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
```

- [ ] **Step 2: Rodar e confirmar que falha pelo motivo certo**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/src/hub
terraform test -no-color -filter=tests/waf.tftest.hcl 2>&1 | tail -20
```

Esperado: falha com `Reference to undeclared data resource` para `data.aws_wafv2_managed_rule_group.common`.

- [ ] **Step 3: Acrescentar o data source e o bloco `rule` do CommonRuleSet**

No `waf.tf`, **antes** do `resource "aws_wafv2_web_acl" "hub"`:

```hcl
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
```

E, dentro do `aws_wafv2_web_acl.hub`, **depois** do bloco `rule` da rate-limit:

```hcl
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
```

- [ ] **Step 4: Rodar e confirmar que passa**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/src/hub
terraform test -no-color -filter=tests/waf.tftest.hcl 2>&1 | tail -20
```

Esperado: `Success!` — nenhum run falhando.

- [ ] **Step 5: Provar que o override_data não está mascarando um teste vazio**

Se o `override_data` fosse removido, o data source devolveria `[]` e as asserções de conteúdo cairiam. Confirmar que a asserção depende mesmo dos dados injetados:

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/src/hub
python3 - <<'PY'
p = "tests/waf.tftest.hcl"
s = open(p).read()
s = s.replace('{ name = "GenericLFI_URIPATH" },', '', 1)
open(p, "w").write(s)
PY
grep -c "GenericLFI_URIPATH" tests/waf.tftest.hcl
terraform test -no-color -filter=tests/waf.tftest.hcl 2>&1 | tail -12
```

Esperado: `grep -c` devolve `1` (sobrou só a asserção que espera o nome) e o run `o_common_rule_set_nasce_inteiro_em_count` **falha** nas asserções de contagem e de conjunto — prova de que elas leem a lista de verdade.

Reverter e reconfirmar:

```bash
git checkout tests/waf.tftest.hcl
terraform test -no-color -filter=tests/waf.tftest.hcl 2>&1 | tail -5
```

Esperado: `Success!` — nenhum run falhando.

- [ ] **Step 6: Commit**

```bash
cd /home/silvios/git/wasp-idp
git add aws/terraform/src/hub/waf.tf aws/terraform/src/hub/tests/waf.tftest.hcl
git commit -m "$(cat <<'EOF'
feat(#84): CommonRuleSet em Count, com override por regra

Os nomes das regras vem do data source aws_wafv2_managed_rule_group, nao
de lista fixa: uma lista mantida a mao envelheceria em silencio e regra
nova da AWS nasceria bloqueando sem ninguem decidir.

O Count vem de rule_action_override POR REGRA, e o override_action do
grupo fica sempre `none` — a AWS e explicita que o override do grupo
inteiro "is not a good option for testing", porque esconde qual regra
casou.

Sob mock_provider o data source devolve [], entao as assercoes exigem
override_data; dois runs com listas de tamanhos diferentes provam que a
lista vem do data source e nao do codigo.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01EybnMkQ3zJpCehCEijs392
EOF
)"
```

---

## Task 3: Os três managed rule groups restantes

Replica o padrão da Task 2 para IpReputation (`70`), KnownBadInputs (`81`) e SQLi (`90`).

**Files:**
- Modify: `aws/terraform/src/hub/waf.tf`
- Test: `aws/terraform/src/hub/tests/waf.tftest.hcl` (acrescentar um run ao fim)

**Interfaces:**
- Consumes: o padrão de bloco `rule` da Task 2
- Produces: `data.aws_wafv2_managed_rule_group.{ip_reputation,known_bad_inputs,sqli}`

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar ao fim de `tests/waf.tftest.hcl`:

```hcl
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
```

- [ ] **Step 2: Rodar e confirmar que falha pelo motivo certo**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/src/hub
terraform test -no-color -filter=tests/waf.tftest.hcl 2>&1 | tail -20
```

Esperado: falha no run novo — `one()` sobre lista vazia devolve `null` ao procurar `aws-ip-reputation`, e a comparação falha. Os 8 runs anteriores continuam passando.

- [ ] **Step 3: Acrescentar os três data sources**

No `waf.tf`, junto ao `data.aws_wafv2_managed_rule_group.common`:

```hcl
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
```

- [ ] **Step 4: Acrescentar os três blocos `rule`**

No `aws_wafv2_web_acl.hub`. O de IP reputation vai **antes** do `aws-common-rule-set` (leitura na ordem de avaliação); os outros dois, depois.

```hcl
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
```

- [ ] **Step 5: Rodar e confirmar que passa**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/src/hub
terraform test -no-color -filter=tests/waf.tftest.hcl 2>&1 | tail -20
```

Esperado: `Success!` — nenhum run falhando.

- [ ] **Step 6: Rodar a regressão inteira do módulo**

As tasks anteriores só rodaram o arquivo novo. Confirmar que nada quebrou nos outros cinco:

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/src/hub
nohup terraform test -no-color > /tmp/claude-1000/hub-regression.log 2>&1 < /dev/null & disown
sleep 60; tail -20 /tmp/claude-1000/hub-regression.log
```

A regressão do módulo passa de 2 min — por isso vai em background. Esperado ao fim: `Success!` sem nenhum `failed` maior que zero. Se `sleep 60` não bastar, reler o log; **não** matar o processo.

- [ ] **Step 7: Commit**

```bash
cd /home/silvios/git/wasp-idp
git add aws/terraform/src/hub/waf.tf aws/terraform/src/hub/tests/waf.tftest.hcl
git commit -m "$(cat <<'EOF'
feat(#84): IP reputation, KnownBadInputs e SQLi no Web ACL do hub

Completa os quatro managed rule groups. IpReputationList nao estava na
#83: entrou porque o guia prescritivo da AWS o trata como baseline, custa
25 WCU e nao cobra por request.

A ordem segue a tabela recomendada pela AWS (rate 50, ip-reputation 70,
CRS 80, KnownBadInputs 81, SQLi 90) e esta coberta por assercao. Em Count
nada termina a avaliacao, entao a ordem e inocua hoje e decisiva no dia da
promocao — quando ninguem vai lembrar de conferir.

Total: 1.125 WCU dos 1.500 inclusos no preco basico.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01EybnMkQ3zJpCehCEijs392
EOF
)"
```

---

## Task 4: Documentar o WAF como camada L7

**Files:**
- Modify: `aws/docs/network/06-security.md`

**Interfaces:**
- Consumes: nada de código
- Produces: nada que outra task use

- [ ] **Step 1: Acrescentar o WAF ao diagrama de camadas**

Em `aws/docs/network/06-security.md`, substituir o bloco `text` da seção "Camadas de defesa (defense in depth)" por:

```text
1. Conta (blast radius)          ← tópico 3
2. TGW route table por spoke     ← tópico 3  (o que um spoke pode ROTEAR)
3. WAF no ALB do hub (L7)        ← este tópico (o que o CONTEÚDO da request revela)
4. Security Group (stateful)     ← este tópico (o que um recurso ACEITA)
5. NACL (stateless, por subnet)  ← este tópico (guarda grossa por subnet)
6. VPC Flow Logs (detecção)      ← este tópico (o que de fato TRAFEGOU)
```

- [ ] **Step 2: Acrescentar a seção do WAF**

Inserir **antes** da seção `## Security Groups (stateful — a camada primária)`:

```markdown
## AWS WAF (camada 7 — o que o conteúdo da request revela)

Security Group e NACL decidem por endereço e porta; nenhum dos dois abre a request. O ALB do hub
é o único ponto de entrada público do desenho, e é onde a inspeção de conteúdo faz sentido — um
`aws_wafv2_web_acl` regional associado a ele ([SEC05-BP03 — Implement inspection-based
protection](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_network_protection_inspection.html)).

Quatro managed rule groups da AWS, mais uma rate-based rule, nesta ordem de avaliação — a
[recomendada pela AWS](https://aws.github.io/aws-security-services-best-practices/guides/waf/),
cujo princípio é "block the most traffic, at the lowest cost, as early as possible":

| Priority | Regra | O que cobre |
|---|---|---|
| `50` | Rate-based (por IP, janela de 300s) | Abuso volumétrico e DoS de camada 7 |
| `70` | `AWSManagedRulesAmazonIpReputationList` | Origens sabidamente maliciosas ou ofuscadas |
| `80` | `AWSManagedRulesCommonRuleSet` | XSS, LFI, RFI, anomalias de request |
| `81` | `AWSManagedRulesKnownBadInputsRuleSet` | Exploits conhecidos (Log4j, desserialização Java) |
| `90` | `AWSManagedRulesSQLiRuleSet` | SQL injection |

**Tudo nasce em `Count`, e isso é uma decisão com prazo, não o estado desejado.** A AWS manda
tunar com tráfego de produção antes de bloquear, e este ALB ainda não tem esse tráfego. A
promoção é uma troca de parâmetro (`waf_managed_rules_action = "block"`); o critério está em
[`docs/superpowers/specs/2026-09-02-waf-web-acl-hub-alb-design.md`](../../../docs/superpowers/specs/2026-09-02-waf-web-acl-hub-alb-design.md).

Enquanto a postura for `Count`, a observação vem de `rule_action_override` **por regra** (métrica
e label individuais), não do override do grupo inteiro — a AWS é explícita que o segundo *"is not
a good option for testing the rules in a rule group"*, porque devolve um contador só e esconde
qual regra casou.

**O que o WAF não faz:** o `default_action` é `allow`. Request que não casa nenhuma regra passa —
o WAF filtra o que reconhece como malicioso, não autoriza o que conhece. Autorização continua
sendo do Security Group (rede) e do Istio/aplicação (identidade).

**Custo e capacidade:** US$ 5/mês pelo Web ACL, US$ 1/mês por rule group ou rule (cinco aqui) e
US$ 0,60 por milhão de requests — prorateado por hora, e esta camada é destruída todo dia. Os
grupos consomem 1.125 WCU dos 1.500 inclusos no preço básico, o que deixa pouca folga para um
segundo grupo grande.
```

- [ ] **Step 3: Acrescentar a linha na tabela Well-Architected**

Na tabela `## Well-Architected — porquê`, a linha de `SEC05-BP03` hoje é:

```markdown
| **[SEC05-BP03 — Implement inspection-based protection](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_network_protection_inspection.html)** | Gateway/Interface endpoints evitam exposição pública |
```

Substituir por:

```markdown
| **[SEC05-BP03 — Implement inspection-based protection](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_network_protection_inspection.html)** | WAF no ALB do hub inspeciona L7; Gateway/Interface endpoints evitam exposição pública |
```

- [ ] **Step 4: Conferir os links relativos**

O doc está em `aws/docs/network/`, e o link para a spec sobe três níveis. Conferir que o caminho resolve:

```bash
cd /home/silvios/git/wasp-idp/aws/docs/network
ls -la ../../../docs/superpowers/specs/2026-09-02-waf-web-acl-hub-alb-design.md
```

Esperado: o arquivo é listado. Se não, corrigir o número de `../` antes de commitar — link quebrado em doc é o tipo de erro que ninguém vê até precisar dele.

- [ ] **Step 5: Commit**

```bash
cd /home/silvios/git/wasp-idp
git add aws/docs/network/06-security.md
git commit -m "$(cat <<'EOF'
docs(#84): WAF como camada L7 no defense in depth da rede

O diagrama de camadas ia da route table do TGW direto ao security group;
faltava a unica camada que abre a request. Documenta a ordem das regras e
o porque dela, a postura Count com prazo, e o que o WAF NAO faz — o
default_action e allow, entao ele filtra o que reconhece, nao autoriza o
que conhece.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01EybnMkQ3zJpCehCEijs392
EOF
)"
```

---

## Verificação final (antes de abrir o PR)

- [ ] **Regressão offline completa do módulo**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/src/hub
nohup terraform test -no-color > /tmp/claude-1000/hub-final.log 2>&1 < /dev/null & disown
sleep 90; grep -E "^(Success|Failure)" /tmp/claude-1000/hub-final.log
```

Critério: nenhuma linha `Failure!`.

- [ ] **Regressão da raiz que consome o módulo**

O módulo `src/hub` é consumido por `regions/us-east-1/`. Variável nova com default não quebra a raiz, mas o `.terraform/modules` da raiz pode estar desatualizado:

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/regions/us-east-1
nohup terraform test -no-color > /tmp/claude-1000/region-final.log 2>&1 < /dev/null & disown
sleep 90; grep -E "^(Success|Failure)" /tmp/claude-1000/region-final.log
```

Se acusar `no available releases match` ou não enxergar o módulo novo, rodar `terraform init -reconfigure` na raiz antes — e se o SSO estiver caído, chamar `terraform test` direto, sem `init`.

- [ ] **Confirmar que nada foi aplicado por engano**

```bash
cd /home/silvios/git/wasp-idp && git status --short && git log --oneline main..HEAD
```

Esperado: árvore limpa e quatro commits (mais os dois de doc que já existiam na branch).

## O que só um apply real prova

Fora do escopo da implementação offline, mas é o que fecha a issue:

1. `aws wafv2 get-web-acl-for-resource --resource-arn <alb-arn> --region us-east-1 --profile network --output json > /tmp/assoc.json` — devolve o Web ACL. Prova a associação de verdade; offline ela só existe por override. **Redirecionar para arquivo**: o wrapper `rtk` desta máquina quebra o parsing de JSON em pipe.
2. Uma request com payload óbvio (`?q=<script>alert(1)</script>`) **passa** — porque a postura é `Count` — e aparece nos `sampled_requests` da regra `aws-common-rule-set` no console. Prova as duas coisas ao mesmo tempo: a regra avalia, e a postura é a esperada.
3. As métricas do namespace `AWS/WAFV2` existem com os `metric_name` declarados.
4. **A associação não deve precisar de segundo apply.** Se falhar com `WAFUnavailableEntityException`, o retry de 10 min do provider não bastou e a alavanca é `timeouts { create }` no recurso — não `time_sleep`, não reaplicar.

## Depois desta issue

`waf.tf` fica pronto para receber, sem reestruturação: o logging (#86, um `aws_wafv2_web_acl_logging_configuration` apontando para o Web ACL) e as regras por tenant (#89, `scope_down_statement` por host ou rate rules escopadas). A capacidade restante (~373 WCU) é o limite prático disso.
