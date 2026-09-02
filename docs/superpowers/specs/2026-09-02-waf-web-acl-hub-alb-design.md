# WAF Web ACL on the Hub ALB — Design

Issue [#84](https://github.com/smsilva/wasp-idp/issues/84), primeira de seis da decomposição de [#83](https://github.com/smsilva/wasp-idp/issues/83) (prefixo `[SEC-EDGE]`).

## Contexto

O ALB do hub (`aws_lb.hub`, `aws/terraform/src/hub/main.tf:313`) é `internet-facing`, com listener HTTPS em 443 (`aws_lb_listener.https`, linha 360) e security group aceitando `0.0.0.0/0` em 443 e 80 (linhas 281-299). É o ponto de entrada público único do desenho: cada célula anexa o próprio certificado por SNI e a própria listener rule; host que não casa nenhuma rule recebe um 404 explícito.

Não existe nenhum recurso `aws_wafv2_*` em `aws/terraform/` — o ALB está exposto sem inspeção de camada 7.

A issue original apontava `aws/terraform/src/ingress/main.tf`; aquele módulo é o **NLB interno da spoke**, não o ALB do hub. O caminho correto é `src/hub/`.

**Um item da #83 já estava resolvido antes de começar:** o `ssl_policy` do listener já é `ELBSecurityPolicy-TLS13-1-2-2021-06` (linha 364). Virou a issue #88, de registro apenas.

## Escopo

Entra: Web ACL regional com quatro managed rule groups da AWS e uma rate-based rule, associado ao ALB do hub; as variáveis que controlam a postura de bloqueio; testes offline; documentação.

Não entra (issues irmãs): logging do WAF para o log-archive (#86), access logs do ALB (#85), decisão sobre Shield Advanced (#87), segregação por tenant (#89).

**AWS Firewall Manager fica fora de propósito.** O SEC05-BP03 o cita como o caminho para gerir WAF centralmente numa Organization, que é exatamente a forma desta topologia. Mas Firewall Manager é política aplicada de cima para baixo a partir de uma conta de administrador delegado — decisão de governança multi-conta, não de módulo. Pertence à discussão da #89.

## A decisão que define o resto: `Count` agora, `Block` na entrada em produção

O guia prescritivo da AWS ([AWS Security Services Best Practices — WAF](https://aws.github.io/aws-security-services-best-practices/guides/waf/), o mesmo que o [SEC05-BP03](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_network_protection_inspection.html) cita como referência) é explícito: o estado-alvo de produção é `Block`. A tabela de ordem recomendada traz `Action = Block` para rate-based, para os baseline AMRs e para os use-case AMRs. E por grupo:

| Grupo | O que o guia diz |
|---|---|
| Known Bad Inputs | *"frequently has a low false positive rate and low WCU cost, making it a good candidate to **enforce early in a deployment**"* |
| SQL Database | *"performs SQL injection inspection... at a **low sensitivity level**. This means it catches well-known SQLi patterns while **minimizing false positives**"* |
| Core Rule Set | *"the rule group **most likely to produce false positives**"* — mas *"your goal should be to **enforce as many rules in this group as possible** — but it does not need to be every single rule"* |

**Mesmo assim, esta entrega nasce inteira em `Count`.** Não por discordar do guia, mas porque o guia pressupõe um passo que ainda não foi dado: *"test and tune the rules **in count mode with your production traffic** before enabling them"* ([Testing and tuning your AWS WAF protections](https://docs.aws.amazon.com/waf/latest/developerguide/web-acl-testing.html)). Este ALB ainda não tem tráfego de produção para tunar contra, e o logging do WAF (#86) — que é onde o campo `terminatingRule` diz qual regra casou — ainda não existe.

A decisão, então, é **explícita e com data de validade**: `Count` é o estado de bootstrap, não o estado desejado. A promoção para `Block` é uma troca de parâmetro (`waf_managed_rules_action = "block"`), não uma reescrita — e a spec registra o critério para fazê-la:

> **Critério de promoção para `Block`:** quando o ALB do hub receber tráfego de produção **e** a #86 (logging do WAF) estiver aplicada, revisar as métricas CloudWatch e os `sampled_requests` por pelo menos um ciclo de tráfego representativo. Promover `waf_managed_rules_action` para `"block"`, tratando os falsos positivos que aparecerem com `rule_action_override` cirúrgico (o mecanismo que a AWS recomenda) em vez de rebaixar o grupo inteiro de volta a `Count`.

O guia já nomeia as regras que provavelmente vão precisar desse tratamento no CRS, e vale registrá-las agora para quem for fazer a promoção não redescobrir:

- **`SizeRestrictions_BODY`** — bloqueia body acima de 8 KB; quebra upload de arquivo e JSON grande.
- **`CrossSiteScripting_BODY`** — dispara em conteúdo que parece HTML/script: `.docx`, `.xml`, `.svg`, editores rich text.
- **`CrossSiteScripting_QUERYARGUMENTS`** e **`CrossSiteScripting_COOKIE`** — menos comuns, mas disparam em aplicação que passa fragmento de HTML ou conteúdo codificado em query string ou cookie.

### Terminologia: por que `Count` e não `Allow` ou `Log`

`Log` não existe como rule action no AWS WAF. `Allow` existe, mas a [doc](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-action.html) é explícita: *"Allow – AWS WAF allows the request to be forwarded to the protected AWS resource... **This is a terminating action**"* — a request seria liberada na hora, **pulando todas as regras seguintes**. Seria um bypass, não uma observação.

`Count` é o termo oficial: *"AWS WAF counts the request but does not determine whether to allow it or block it. **This is a non-terminating action.** AWS WAF continues processing the remaining rules"*.

`Allow` aparece uma vez neste desenho, e no lugar certo: como `default_action` do Web ACL — o que acontece com a request que não casa **nenhuma** regra. Fail-open é o valor correto para um WAF na frente de um ALB público; fail-closed derrubaria o site inteiro.

## Ordem das regras

A ordem é a decisão de maior impacto num Web ACL, porque ações terminantes param a avaliação. As prioridades seguem a [tabela de ordem recomendada](https://aws.github.io/aws-security-services-best-practices/guides/waf/) do guia, multiplicadas por 10 para deixar espaço de inserção sem renumerar o que já existe:

| Priority | Regra | Posição no guia | Por quê |
|---|---|---|---|
| `50` | Rate-based (blanket) | 5 | *"stop volumetric abuse early before it consumes capacity in more expensive downstream rules"* |
| `70` | `AWSManagedRulesAmazonIpReputationList` | 7 | Origens sabidamente maliciosas, avaliação barata |
| `80` | `AWSManagedRulesCommonRuleSet` | 8 | Cobertura ampla (XSS, LFI, RFI, anomalias) |
| `81` | `AWSManagedRulesKnownBadInputsRuleSet` | 8 | Exploits conhecidos (Log4j, deserialização Java) |
| `90` | `AWSManagedRulesSQLiRuleSet` | 9 | Use-case: SQL injection |

O princípio declarado pelo guia: *"block the most traffic, at the lowest cost, as early as possible"*.

A rate-based rule vir **antes** dos managed rule groups é o ponto que mais importa quando a promoção para `Block` acontecer — em `Count` nada termina a avaliação, então a ordem é inócua hoje e decisiva depois. Escrever a ordem certa agora evita ter de repensá-la no momento em que o risco for real.

`AWSManagedRulesAmazonIpReputationList` não estava na #83. Entrou porque o guia o trata como baseline recomendado, custa 25 WCU e não tem cobrança por request — o benefício marginal é alto e o custo marginal é o mesmo US$ 1/mês de qualquer rule group.

## Recursos

Arquivo novo `aws/terraform/src/hub/waf.tf` — o `main.tf` já tem 394 linhas, e o WAF é uma unidade coesa, testável isolada. O Terraform funde todos os `.tf` do diretório; não muda nada para quem consome o módulo.

```
aws_wafv2_web_acl.hub                 name = "${var.name}-ingress-waf", scope = REGIONAL
                                      default_action { allow {} }
                                      visibility_config (obrigatório)
                                      5 blocos rule (as da tabela acima)
aws_wafv2_web_acl_association.hub     resource_arn = aws_lb.hub.arn
                                      web_acl_arn  = aws_wafv2_web_acl.hub.arn
```

Fatos do schema do provider (`aws` 6.62.0), verificados com `terraform providers schema -json`, não de memória:

- **`visibility_config` é obrigatório (`min_items = 1`) no topo E dentro de cada `rule`**, com os três atributos required: `cloudwatch_metrics_enabled`, `metric_name`, `sampled_requests_enabled`. Isso não é burocracia: com `sampled_requests_enabled = true`, o console mostra amostra das requests que cada regra contou — **é a observabilidade que torna a decisão de promoção possível sem depender da #86**.
- Regra com `managed_rule_group_statement` usa **`override_action`** (`count` | `none`); regra com `rate_based_statement` usa **`action`** (`allow` | `block` | `captcha` | `challenge` | `count`). Não são intercambiáveis.
- `rate_based_statement` exige só `limit`; `aggregate_key_type` e `evaluation_window_sec` são opcionais. A janela **não** é fixa em 5 minutos: *"Valid settings are 60 (1 minute), 120 (2 minutes), 300 (5 minutes), and 600 (10 minutes), and 300 (5 minutes) is the default"*. Fica explícita no código para não parecer acidental.
- A rate-based rule **não aceita `Allow`**: *"You can use any rule action except Allow"*. Sem efeito prático aqui (a variável só admite `count` e `block`), mas fecha a porta para alguém tentar.
- Custo de capacidade da rate-based rule: **2 WCU** de base.
- `managed_rule_group_statement` aceita `rule_action_override` (máximo 100 por grupo) — o mecanismo da promoção cirúrgica descrita acima.
- **O `version` do managed rule group fica sem fixar**, usando a versão default que a AWS atualiza sozinha com proteções novas. Fixar traria previsibilidade e a armadilha de rotação — mesma família do `thumbprint_list` do OIDC já documentada em `aws/terraform/CLAUDE.md`. Com a postura em `Count`, uma regra nova entrando no grupo não bloqueia nada por surpresa; é o momento certo de aceitar a atualização automática.

**O nome do Web ACL não precisa da região.** WAFv2 `REGIONAL` é por região, ao contrário do `aws_iam_saml_provider` (IAM é global) e do FQDN do endpoint da VPN (a subzona é uma só) — os dois casos que forçaram `var.region` a existir neste módulo e que quebraram a segunda região. Escrito aqui porque a pergunta vai voltar.

## Como os overrides de `Count` são gerados

Com a postura em `Count` e o mecanismo `rule_action_override` (que dá métrica e label **por regra**, ao contrário do `override_action = count` no grupo inteiro), é preciso nomear as regras. São 46:

| Grupo | Regras | Capacity |
|---|---|---|
| `AWSManagedRulesCommonRuleSet` | 22 | 700 WCU |
| `AWSManagedRulesKnownBadInputsRuleSet` | 12 | 200 WCU |
| `AWSManagedRulesSQLiRuleSet` | 9 (4 já nativamente em `Count`) | 200 WCU |
| `AWSManagedRulesAmazonIpReputationList` | 3 (1 já nativamente em `Count`) | 25 WCU |

A AWS distingue dois mecanismos, e a distinção é o motivo desta seção existir. Sobre o override do grupo inteiro, a [doc](https://docs.aws.amazon.com/waf/latest/developerguide/web-acl-rule-group-override-options.html) diz: *"**This is not a good option for testing the rules in a rule group**, because it doesn't alter how AWS WAF evaluates the rule group itself."* Com ele, vê-se um contador do grupo e não se sabe **qual** das 22 regras do CRS disparou — que é exatamente a informação necessária para decidir a promoção.

**Decisão: derivar os nomes do data source `aws_wafv2_managed_rule_group`**, um por grupo, com `dynamic "rule_action_override"` sobre `rules[*].name`.

```hcl
data "aws_wafv2_managed_rule_group" "common" {
  name        = "AWSManagedRulesCommonRuleSet"
  vendor_name = "AWS"
  scope       = "REGIONAL"
}
```

O trade-off, honesto nas duas direções:

- **A favor:** 46 nomes fixos no código envelhecem em silêncio — quando a AWS acrescentar uma regra ao grupo, ela nasceria **bloqueando** sem ninguém ter decidido isso, que é precisamente o modo de falha que a postura `Count` existe para evitar. Com o data source, regra nova entra em `Count` sozinha.
- **Contra:** o plan passa a fazer quatro chamadas `DescribeManagedRuleGroup` (exige `wafv2:DescribeManagedRuleGroup` na role que roda o plan) e deixa de ser puramente offline.
- **Mitigação natural:** quando a promoção para `Block` acontecer, `waf_managed_rules_action = "block"` zera a lista de overrides e os data sources deixam de influenciar o resultado. O acoplamento existe só enquanto a postura é de observação.

**Esta é a decisão do design com menos convicção** — um `locals` com os 46 nomes é defensável, e troca manutenção por independência de rede no plan. Marcada aqui para receber atenção na revisão.

## Variáveis

Duas, ambas com default `"count"` e validação `contains(["count", "block"], ...)`:

| Variável | Default | Efeito |
|---|---|---|
| `waf_managed_rules_action` | `"count"` | `count` gera `rule_action_override` para todas as regras dos quatro grupos; `block` zera a lista e cada grupo passa a aplicar a ação nativa das suas regras |
| `waf_rate_limit_action` | `"count"` | `count` ou `block` no `action` da rate-based rule |

Mais `waf_rate_limit` (number, default `2000`, validação `>= 10`): requests por IP na janela de 300s.

O piso é 10, não 100: *"The lowest limit setting allowed is 10"*. (Durante o desenho eu afirmei 100 — erro; o mínimo foi reduzido pela AWS e a doc atual diz 10. A validação segue o valor da doc, não a lembrança.)

**São duas variáveis e não uma de propósito.** A rate-based rule é a única do conjunto que mitiga DoS de camada 7, e é a de falso positivo mais previsível — provavelmente será a primeira a ser promovida, antes dos managed rule groups. Uma variável só forçaria promover tudo junto.

> **Nota para a revisão:** a decisão anterior nesta conversa foi rate-based em `Block` desde o dia 1; a decisão final foi "manter tudo em `Count`". Interpretei que isso inclui a rate-based rule, e por isso o default dela é `"count"`. Se a intenção era manter a rate em `Block`, é uma linha de default a mudar.

## Testes

Arquivo novo `aws/terraform/src/hub/tests/waf.tftest.hcl`, com o mesmo bloco de `variables` e os mesmos overrides de `ingress-alb.tftest.hcl` (`module.network`, `data.aws_route53_zone.subzone`, `aws_ec2_transit_gateway.hub.arn`) — sob `command = plan` a configuração inteira é avaliada, não só o que a asserção toca.

Três armadilhas foram **verificadas empiricamente** antes de escrever esta seção, e cada uma muda o desenho do teste:

**1. `rule` é um SET, não uma lista.** `nesting_mode: set` no schema. Acesso por índice não compila (`Cannot index a set value`) — é a armadilha já catalogada em `aws/terraform/CLAUDE.md`. As asserções filtram por nome:

```hcl
condition = length([
  for r in aws_wafv2_web_acl.hub.rule : r if r.name == "rate-limit"
]) == 1
```

**2. Sob `mock_provider`, o data source devolve `rules = []`.** Confirmado com um spike descartável: `MOCK rules = [] | count = 0`. Consequência: um `dynamic` alimentado pelo data source gera **zero** overrides no teste, e qualquer asserção do tipo `alltrue([for o in overrides : ...])` passa **verde e vazia** — a armadilha `alltrue([])` que este repo já catalogou. As asserções sobre overrides exigem `override_data` explícito injetando uma lista conhecida.

**3. Um `override_data` prova o VALOR; dois provam a LIGAÇÃO.** Com uma lista só, uma implementação que colasse os nomes à mão passaria verde. Dois runs, com listas de **tamanhos diferentes**, e nenhuma lista fixa satisfaz os dois.

O que os runs cobrem:

- Os quatro managed rule groups presentes, com `vendor_name = "AWS"` e o nome certo.
- A ordem: `priority` da rate-based menor que a de todos os managed groups. É a asserção que protege a decisão de ordem quando ela passar a importar de verdade.
- `default_action` é `allow` (fail-open deliberado).
- `visibility_config` com `sampled_requests_enabled = true` no topo e em cada regra — é a observabilidade da qual a promoção depende.
- Rate-based: `limit = 2000`, `aggregate_key_type = "IP"`, `evaluation_window_sec = 300`.
- Com `waf_managed_rules_action = "count"` (default), os overrides cobrem toda a lista injetada; com `"block"`, a lista de overrides é **vazia**. Segundo run, mutação real.
- A associação aponta para o ALB do hub.

**A associação exige cuidado extra.** `aws_wafv2_web_acl.hub.arn` e `aws_lb.hub.arn` são ambos computed — asserção entre dois computados dá *"Unknown condition value"*, armadilha já catalogada. A saída é `override_resource` em `aws_lb.hub`, que **substitui os computados por inteiro**: precisa injetar `arn`, `dns_name` **e** `zone_id`, porque os três têm consumidores (`outputs.tf`, linhas 38/48/53). Omitir um quebra o plan por artefato de teste, e o erro aponta para o lugar errado. Dois runs com ARNs diferentes, pela mesma razão do item 3.

**O que não vai ser coberto, e por quê:** o `terraform test` recusa `condition = false` (*"The condition expression must refer to at least one object"*) — mesma família da lição sobre mutar `validation` já registrada. Não afeta as asserções acima; fica escrito porque custou um ciclo no spike.

## Custo e capacidade

| Item | Valor |
|---|---|
| Web ACL | US$ 5,00/mês |
| Rule groups + rules | US$ 1,00/mês × 5 (4 managed groups + 1 rate-based) |
| Requests | US$ 0,60 por milhão |
| **Total parado** | **US$ 10,00/mês**, *prorateado por hora* |

O prorateio horário importa aqui mais que o valor: esta camada é destruída todo dia (o próprio comentário em `main.tf:265` registra que o teardown noturno leva o ingress público junto). O custo real é fração do valor mensal.

**Capacidade:** 700 + 200 + 200 + 25 = 1.125 WCU dos **1.500 inclusos** no preço básico (teto absoluto 5.000, e acima de 1.500 há [cobrança adicional em tiers](https://docs.aws.amazon.com/waf/latest/developerguide/aws-waf-capacity-units.html)). A rate-based rule custa 2 WCU. Sobram ~373 — cabe uma regra custom ou um grupo pequeno; **não** cabe um segundo grupo grande (Bot Control, ATP) sem sair do tier básico. Registrado porque a #89 (segregação por tenant) pode querer regras por spoke.

## Armadilha conhecida de apply

A [doc](https://docs.aws.amazon.com/waf/latest/developerguide/web-acl-testing.html) avisa sobre inconsistência temporária na propagação, e um dos exemplos é exatamente o que este design faz num apply só: *"After you create a protection pack (web ACL), if you try to associate it with a resource, you might get an exception indicating that the web ACL is unavailable."*

Propagação de segundos a minutos. Se o apply falhar na associação logo após criar o Web ACL, é isso — e um segundo apply resolve, sem recurso órfão. Registrado para não virar caça a bug inexistente.

## Verificação

Offline, o critério é `0 falhas` no `terraform test` do módulo `src/hub` (todos os arquivos, não só o novo — a regressão inteira passa de 2 min, então roda em background ou por diretório, sempre com `-no-color`).

Num apply real, três perguntas que o teste offline não responde:

1. `aws wafv2 get-web-acl-for-resource --resource-arn <alb-arn>` devolve o Web ACL — prova a associação de verdade, que offline só é assertável por override.
2. Uma request maliciosa óbvia (ex.: `?q=<script>alert(1)</script>`) **passa** — porque a postura é `Count` — e aparece nos `sampled_requests` da regra correspondente. Isso prova simultaneamente que a regra avalia e que a postura é a esperada.
3. As métricas CloudWatch do namespace `AWS/WAFV2` existem por regra, com o `metric_name` declarado.

## Riscos e itens abertos

- **A origem dos 46 nomes** (data source vs. `locals`) é a decisão de menor convicção do design — ver a seção própria.
- **`Count` não protege.** Enquanto a promoção não acontecer, esta issue entrega observabilidade e a estrutura, não mitigação. É uma decisão consciente com critério de saída escrito, não um esquecimento — mas se o ALB receber tráfego real antes da promoção, o gap é real.
- **`AWSManagedRulesSQLiRuleSet` pode não se aplicar.** O guia avisa que grupo use-case fora do stack *"consumes WCU capacity... and in some cases can introduce unnecessary false positives"*. O ALB do hub roteia para células genéricas; se nenhuma falar com SQL, os 200 WCU não se pagam. Fica porque a #83 o pediu explicitamente e o custo cabe no tier.
- **Anti-DDoS AMR e Shield Advanced** ficam fora — o primeiro tem cobrança por request, o segundo é a #87.

## Próximo passo

Plano de implementação (skill `writing-plans`), com o primeiro passo sendo a validação do comportamento do data source sob `mock_provider` — o spike já mostrou que devolve lista vazia, e o plano precisa que a asserção nasça provando algo em vez de passar vazia.
