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
| 7 | [`07-cloudtrail-e-log-archive.md`](07-cloudtrail-e-log-archive.md) | Trail organizacional, conta `log-archive`, bucket de auditoria em conta separada | Security |

**Vocabulário:** nomes de OU e de conta seguem o whitepaper *Organizing Your AWS Environment
Using Multiple Accounts* (`Security`, `Infrastructure`, `Workloads/NonProd`,
`Workloads/Production`; conta de rede = `network`). Divergir do whitepaper só com motivo
registrado.

## Sequência de construção (conta vazia → contas prontas)

```text
① Login na 1ª conta (a que você já tem) — ela vira a conta de GERÊNCIA da Organization
② Habilitar AWS Organizations nessa conta (all features, não "consolidated billing only")
③ Criar OUs: Security, Infrastructure, Workloads/NonProd, Workloads/Production
④ Conta log-archive (OU Security) + CloudTrail organizacional   ← ANTES de tudo o mais
⑤ Criar a conta network (Connectivity Account) na OU Infrastructure
⑥ Aplicar SCPs baseline na Organization/OUs (guardrails preventivos)
⑦ Configurar IAM Identity Center (SSO) — permission sets por conta, sem usar root
⑧ Por projeto: create-account em NonProd → validar → só então create-account em Production
⑨ Dentro da conta do projeto: provisionar a(s) spoke(s) de rede (→ domínio network)
```

- **④ o quanto antes** — sem trilha desde o início, perde-se o rastro do próprio bootstrap,
  que é quando se opera com privilégio máximo.
- **⑤ e ⑧:** `create-account` **não** aceita OU de destino — a conta nasce na Root e é movida
  depois. São dois passos, e o SCP da OU não vale na janela entre eles.
- **⑥:** SCP não afeta a conta de gerência. Por isso ela não hospeda nada.
- **⑧ uma conta por projeto POR AMBIENTE** (`<projeto>-nonprod`, `<projeto>-prod`) — a conta
  é o único limite forte de quota, SCP, IAM e billing (ver `01-organizations-e-ous.md`).

## Scripts (`scripts/`)

Implementação executável dos passos acima. Cada script é idempotente (reaproveita o que já
existir) e nenhum é destrutivo. Ver `--help` de cada um para detalhes.

| Script | Cobre o passo | O que faz |
|---|---|---|
| `check` | pré-requisito | Valida `aws`/`jq`, credenciais, feature-set da Organization atual |
| `enable-organization` | ② | `create-organization --feature-set ALL` (ou upgrade se já existir em modo consolidado) |
| `create-organizational-unit-structure` | ③ | Cria `Security`, `Infrastructure`, `Workloads/NonProd`, `Workloads/Production` |
| `enable-service-access --service <principal>` | ④ pré-requisito | Trusted access de um serviço na Org (`cloudtrail.amazonaws.com` para o trail; `account.amazonaws.com` para o `rename-account`) |
| `create-log-archive-bucket` | ④ | Assume role na `log-archive` e cria o bucket de auditoria (BPA, versionamento, SSE, policy do CloudTrail) |
| `create-organization-trail` | ④ | Cria o trail organizacional multi-region + `start-logging` + validação de integridade |
| `create-account --ou {security\|infrastructure\|nonprod\|production}` | ④ ⑤ ⑧ | Cria 1 conta e move para a OU pedida. `--ou production` avisa explicitamente antes de prosseguir |
| `apply-baseline-service-control-policy` | ⑥ | Guardrails do tópico 2: restringe região, exige IMDSv2, nega root, protege CloudTrail/saída da Org |
| `assign-permission-set --account <conta> --user\|--group <principal>` | ⑦ | Cria/reusa permission set do Identity Center e atribui à conta — tira a conta do limbo do switch-role |
| `rename-account --name <atual> --new-name <novo>` | correção | Renomeia conta-membro via `account put-account-name`. Só o nome; o e-mail do root user **não** muda |
| `rename-organizational-unit --name <atual> --new-name <novo>` | correção | Renomeia OU in-place — o Id não muda, SCPs e contas seguem válidos |

Rodar manualmente via `! <script>` quando decidir aplicar (o classifier de auto-mode pode
bloquear os que criam recursos reais — se bloquear, o usuário roda via `!`).

**Convenção de execução:** ao rodar um script contra uma conta real, atualizar a doc na
sequência ANTES do próximo — o tópico correspondente (gotchas/comandos descobertos) e o

## Decisões em aberto

| # | Decisão | Por que está aberta | Custo de adiar |
|---|---|---|---|
| 1 | **Retenção do bucket de auditoria** — lifecycle rule (Standard → Glacier após N dias, expiração após M anos) | Janela de retenção é decisão de compliance, não técnica | Único custo do CloudTrail que cresce sozinho e para sempre. Baixo hoje (centavos/mês); revisitar antes de o acervo passar de alguns GB |
| 2 | **Permission set de rotina na `log-archive`** — hoje está `AdministratorAccess` (bootstrap); deveria ser `ReadOnlyAccess` | Ainda não há operação de rotina ali | Enquanto for admin, quem é auditado pode apagar o acervo — anula o motivo de a conta existir |
| 3 | **Conta `security-tooling`** — slot desenhado, conta não criada | Sem GuardDuty/Config/Security Hub habilitados ainda | Nenhum hoje; vira pré-requisito quando a detecção entrar |

## Estado atual vs. alvo (resumo)

- **Hoje no PoC:** uma única conta AWS (`<account-id>`, ver `../../CLAUDE.md`), **não
  dedicada** e **não organizada** — hospeda também infra de outros sistemas/domains, sem
  Organization própria.
- **Alvo desta referência:** Organization própria, conta de gerência apenas administrativa,
  conta network dedicada, conta por projeto.
- **Gap crítico:** a conta atual do PoC não pode virar a "conta network" da referência sem
  antes ser isolada — ela já tem residentes de outros domínios. A adoção da referência a
  partir do PoC exige migrar para uma Organization nova (ou uma OU dedicada, se a Organization
  já existir), não reaproveitar a conta como está.