# `accounts/` — Domain: Accounts and Organizations

Índice de leitura. Convenções e regras ficam em [`CLAUDE.md`](CLAUDE.md).

## O que este domínio entrega

Sair de uma **conta AWS vazia** (a primeira que você loga) e chegar a uma **AWS Organization**
com a estrutura de contas que o hub-and-spoke exige: uma conta de gerência que só administra,
uma **Hub/Connectivity Account** dedicada, e **uma conta por projeto** — cada uma podendo
hospedar 1+ spokes (`../network/00-topology.md`).

## Tópicos

| # | Arquivo | Assunto | Pilar WAF principal |
|---|---|---|---|
| 0 | [`00-strategy.md`](00-strategy.md) | Por que multi-account; papel de cada conta; conta de gerência nunca hospeda workload | Operational Excellence |
| 1 | [`01-organizations-and-ous.md`](01-organizations-and-ous.md) | AWS Organizations, Organizational Units, billing consolidado | Operational Excellence |
| 2 | [`02-scp-guardrails.md`](02-scp-guardrails.md) | Service Control Policies — guardrails preventivos por OU | Security |
| 3 | [`03-provisioning.md`](03-provisioning.md) | Como criar contas de fato: API `create-account`, convenção de e-mail, bootstrap do root | Operational Excellence |
| 4 | [`04-cross-account-access.md`](04-cross-account-access.md) | IAM Identity Center (SSO), permission sets, roles cross-account; nunca usar root | Security |
| 5 | [`05-billing-and-tags.md`](05-billing-and-tags.md) | Billing consolidado, tags de custo por conta/projeto | Cost Optimization |
| 6 | [`06-crossplane-map.md`](06-crossplane-map.md) | O que é (e não é) automatizável via Crossplane; estado atual do PoC vs alvo | — |
| 7 | [`07-cloudtrail-and-log-archive.md`](07-cloudtrail-and-log-archive.md) | Trail organizacional, conta `log-archive`, bucket de auditoria em conta separada | Security |

**Vocabulário:** nomes de OU e de conta seguem o whitepaper *Organizing Your AWS Environment
Using Multiple Accounts* (`Security`, `Infrastructure`, `Workloads/NonProd`,
`Workloads/Production`; conta de rede = `network`). Divergir do whitepaper só com motivo
registrado.
