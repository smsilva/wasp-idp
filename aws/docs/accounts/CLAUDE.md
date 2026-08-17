# CLAUDE.md — `accounts/` (Domínio: Contas e Organizations)

> Índice do domínio **Accounts & Organizations** — o container que hospeda a rede
> (`../network/`). Ordem de leitura = ordem dos arquivos. Corpo genérico (placeholders `<...>`).

## O que este domínio entrega

Sair de uma **conta AWS vazia** (a primeira que você loga) e chegar a uma **AWS Organization**
com a estrutura de contas que o hub-and-spoke exige: uma conta de gerência que só administra,
uma **Hub/Connectivity Account** dedicada, e **uma conta por projeto** — cada uma podendo
hospedar 1+ spokes (`../network/00-topologia.md`).

## Tópicos

| # | Arquivo | Assunto | Pilar WAF principal |
|---|---|---|---|
| 0 | [`00-estrategia-de-contas.md`](00-estrategia-de-contas.md) | Por que multi-account; papel de cada conta; conta de gerência nunca hospeda workload | Operational Excellence |
| 1 | [`01-organizations-e-ous.md`](01-organizations-e-ous.md) | AWS Organizations, Organizational Units, billing consolidado | Operational Excellence |
| 2 | [`02-guardrails-scp.md`](02-guardrails-scp.md) | Service Control Policies — guardrails preventivos por OU | Security |
| 3 | [`03-provisionamento-de-contas.md`](03-provisionamento-de-contas.md) | Como criar contas de fato: API `create-account`, convenção de e-mail, bootstrap do root | Operational Excellence |
| 4 | [`04-acesso-cross-account.md`](04-acesso-cross-account.md) | IAM Identity Center (SSO), permission sets, roles cross-account; nunca usar root | Security |
| 5 | [`05-billing-e-tags.md`](05-billing-e-tags.md) | Billing consolidado, tags de custo por conta/projeto | Cost Optimization |
| 6 | [`06-mapa-crossplane.md`](06-mapa-crossplane.md) | O que é (e não é) automatizável via Crossplane; estado atual do PoC vs alvo | — |

## Sequência de construção (conta vazia → contas prontas)

```text
① Login na 1ª conta (a que você já tem) — ela vira a conta de GERÊNCIA da Organization
② Habilitar AWS Organizations nessa conta (all features, não "consolidated billing only")
③ Criar OUs: Infra, Workloads/Sandbox, Workloads/Production (Sandbox ANTES de Production)
④ Criar a conta Hub (Connectivity Account) dentro da OU Infra
⑤ Aplicar SCPs baseline na Organization/OUs (guardrails preventivos)
⑥ Configurar IAM Identity Center (SSO) — permission sets por conta, sem usar root
⑦ Por projeto: create-account em Sandbox → validar → só então create-account em Production
⑧ Dentro da conta do projeto: provisionar a(s) spoke(s) de rede (→ domínio network)
```

## Scripts (`scripts/`)

Implementação executável dos passos ②–⑤⑦ acima. Cada script é idempotente (reaproveita o
que já existir) e nenhum é destrutivo. Ver `--help` de cada um para detalhes.

| Script | Cobre o passo | O que faz |
|---|---|---|
| `check` | pré-requisito | Valida `aws`/`jq`, credenciais, feature-set da Organization atual |
| `enable-organization` | ② | `create-organization --feature-set ALL` (ou upgrade se já existir em modo consolidado) |
| `create-organizational-unit-structure` | ③ | Cria `Infra`, `Workloads/Sandbox`, `Workloads/Production` — Sandbox sempre antes de Production |
| `apply-baseline-service-control-policy` | ⑤ | Guardrails do tópico 2: restringe região, exige IMDSv2, nega root, protege CloudTrail/saída da Org |
| `create-account --ou {infra\|sandbox\|production}` | ④ ⑦ | Cria 1 conta e move para a OU pedida. `--ou production` avisa explicitamente antes de prosseguir |

Rodar manualmente via `! <script>` quando decidir aplicar (o classifier de auto-mode pode
bloquear os que criam recursos reais — se bloquear, o usuário roda via `!`).

**Convenção de execução:** ao rodar um script contra uma conta real, atualizar a doc na
sequência ANTES do próximo — o tópico correspondente (gotchas/comandos descobertos) e o

## Estado atual vs. alvo (resumo)

- **Hoje no PoC:** uma única conta AWS (`<account-id>`, ver `../../CLAUDE.md`), **não
  dedicada** e **não organizada** — hospeda também infra de outros sistemas/domains, sem
  Organization própria.
- **Alvo desta referência:** Organization própria, conta de gerência apenas administrativa,
  Hub account dedicada, conta por projeto.
- **Gap crítico:** a conta atual do PoC não pode virar a "Hub account" da referência sem
  antes ser isolada — ela já tem residentes de outros domínios. A adoção da referência a
  partir do PoC exige migrar para uma Organization nova (ou uma OU dedicada, se a Organization
  já existir), não reaproveitar a conta como está.