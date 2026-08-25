# 05 — Billing e Tags

**Pilar WAF principal:** Cost Optimization ([COST02 — Governance](https://docs.aws.amazon.com/wellarchitected/latest/cost-optimization-pillar/governance.html)).

## Billing consolidado — o que já vem de graça

Com `feature-set ALL` (tópico 1), toda conta-membro fatura para a management account
automaticamente. Vantagens imediatas, sem configuração:

- **Volume discounts e Savings Plans/Reserved Instances compartilhados** entre contas — o
  desconto por volume da Organization inteira beneficia cada conta-membro.
- **Uma fatura consolidada** — não é preciso somar N faturas manualmente.
- **Isolamento de custo por conta é automático** — o Cost Explorer já separa por
  `linked account`, sem precisar de tag nenhuma para esse nível de granularidade.

## Por que tags ainda importam (granularidade abaixo da conta)

A conta já separa por projeto (se você seguiu a estratégia do tópico 0). Tags entram quando
você precisa de granularidade **dentro** de uma conta — por ambiente, por squad, por
feature — ou quando quer relatórios consolidados que atravessam contas por outro eixo que
não "projeto" (ex.: "quanto custa o time X, somando recursos em 3 contas diferentes").

## Tags recomendadas (baseline)

| Tag | Exemplo | Propósito |
|---|---|---|
| `project` | `<project-name>` | Redundante com a conta, mas útil em relatórios cross-account |
| `environment` | `dev` / `staging` / `prod` | Separa estágio dentro da mesma conta (se aplicável) |
| `owner` | `<team-name>` | Time responsável — contato em caso de incidente/custo alto |
| `managed-by` | `crossplane` / `terraform` / `manual` | Sinaliza IaC — bloqueia edição manual acidental |
| `cost-center` | `<cost-center-id>` | Rateio para FinOps, se a organização tiver centros de custo formais |

## Tag Policies (Organizations) — impor a convenção

AWS Organizations permite **Tag Policies**, que padronizam valores aceitos por tag em toda a
Organization (ex.: `environment` só aceita `dev`/`staging`/`prod`, não `Dev`/`DEV`/`develop`).
Aplicado como as SCPs (tópico 2), por OU ou Organization inteira — mas Tag Policies **não
bloqueiam** a criação de recurso com tag errada (diferente de SCP), só reportam
não-conformidade no Console/Config. Use SCP se o requisito for bloquear, Tag Policy se for
só padronizar/reportar.

## Budgets e alertas

Configurar **AWS Budgets** por conta (ou por tag) com alerta em thresholds (ex.: 80%/100% do
budget mensal) é a rede de segurança contra "esqueci um NAT Gateway rodando" — especialmente
relevante nesta referência, onde TGW + VPN Connections + NAT têm custo por hora fixo
(ver `../network/00-topologia.md` e `04-vpn-acesso.md`).

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **[COST02-BP01 — Develop policies based on your organization requirements](https://docs.aws.amazon.com/wellarchitected/latest/cost-optimization-pillar/cost_govern_usage_policies.html)** | Contas por projeto dão isolamento nativo; tags dão granularidade adicional |
| **[COST02-BP03 — Implement an account structure](https://docs.aws.amazon.com/wellarchitected/latest/cost-optimization-pillar/cost_govern_usage_account_structure.html)** | Tag Policies padronizam valores aceitos |
| **[COST02-BP05 — Implement cost controls](https://docs.aws.amazon.com/wellarchitected/latest/cost-optimization-pillar/cost_govern_usage_controls.html)** | Budgets por conta pegam desvio antes de virar surpresa na fatura |

## Próximo

→ [`06-mapa-crossplane.md`](06-mapa-crossplane.md): o que deste domínio é (e não é)
automatizável via Crossplane, e o estado atual do PoC.
