# CLAUDE.md — `security/` (Domínio: Security & IAM)

> Índice do domínio de **Segurança e IAM** — o perímetro de identidade e os controles que
> permeiam todos os outros domínios. Ordem de leitura = ordem dos arquivos. Corpo genérico (placeholders `<...>`).

## O que este domínio entrega

O **perímetro de identidade** de toda a arquitetura: quem pode agir, com qual privilégio, em
qual conta, e como isso é detectado. Enquanto `../accounts/` decide **onde** as identidades
vivem (SSO na management account, contas por projeto) e `../network/` decide **por onde** o
tráfego passa, este domínio decide **o que cada identidade pode fazer** — humano ou máquina,
dentro de uma conta ou cross-account — e como uma violação vira sinal auditável.

Não repete SSO/permission sets (isso é `../accounts/04-acesso-cross-account.md`); parte dali
e aprofunda: policies escopadas, roles cross-account, perímetro de dados/RAM, identidade de
workload (Pod Identity/IRSA), autenticação de VPN e detecção.

## Tópicos

| # | Arquivo | Assunto | Pilar WAF principal |
|---|---|---|---|
| 0 | [`00-modelo-de-identidade.md`](00-modelo-de-identidade.md) | Humano vs. máquina; as 3 perguntas do perímetro (quem/o quê/onde); credenciais temporárias por padrão | Security (SEC02) |
| 1 | [`01-menor-privilegio-e-policies.md`](01-menor-privilegio-e-policies.md) | Menor privilégio; policies escopadas por ARN; permission boundaries; SCP como teto | Security (SEC03) |
| 2 | [`02-roles-cross-account.md`](02-roles-cross-account.md) | `sts:AssumeRole`, trust policies, `ExternalId`, confused deputy; sem IAM user duplicado por conta | Security (SEC02/SEC03) |
| 3 | [`03-perimetro-de-dados-e-ram.md`](03-perimetro-de-dados-e-ram.md) | Resource-based policies; RAM com escopo por Organization; `allowExternalPrincipals=false` | Security (SEC03) |
| 4 | [`04-identidade-de-workload.md`](04-identidade-de-workload.md) | Automação (Crossplane) sem SSO; IAM user escopado; Pod Identity/IRSA; máquina fora da AWS (Roles Anywhere vs OIDC federation); trajetória k3d→AKS→EKS; segredos no Secrets Manager | Security (SEC02/SEC08) |
| 5 | [`05-autenticacao-vpn.md`](05-autenticacao-vpn.md) | Client VPN (cert/SSO) e site-to-site (PSK); ciclo de vida da credencial; ponte com `../network/04` | Security (SEC02/SEC05) |
| 6 | [`06-deteccao-e-auditoria.md`](06-deteccao-e-auditoria.md) | CloudTrail, IAM Access Analyzer, GuardDuty, credential report; achar privilégio excessivo | Security (SEC04) |
| 7 | [`07-mapa-crossplane.md`](07-mapa-crossplane.md) | O que de IAM é (e não é) provisionável via Crossplane; estado do PoC vs. alvo; bootstrap galinha-e-ovo | — |

## Sequência de construção (perímetro de identidade)

```text
① SSO na management account (→ ../accounts/04) — identidade humana federada, sem IAM user por conta
② Permission sets nomeados por função + permission boundaries por conta (teto de privilégio)
③ Policies escopadas por ARN para cada workload/automação (menor privilégio, não wildcard)
④ Roles cross-account com trust policy escopada (Hub↔projeto) — em vez de duplicar credenciais
⑤ RAM shares com allowExternalPrincipals=false (perímetro: só a própria Organization)
⑥ Identidade de workload no cluster (Pod Identity/IRSA) — pods assumem role, sem access key montada
⑦ Autenticação de VPN (cert/SSO para client; PSK para site-to-site) fechando no Hub
⑧ Detecção sempre ligada (CloudTrail + Access Analyzer + GuardDuty) — violação vira sinal
```

## Estado atual vs. alvo (resumo)

- **Hoje no PoC:** um IAM user dedicado (`crossplane-poc`) com `PowerUserAccess` +
  inline policy escopada às roles `poc-eks-*` opera o Crossplane; humanos entram via SSO
  `AdministratorAccess`. Sem permission boundary, sem Access Analyzer, sem roles
  cross-account (conta única). Ver `../../CLAUDE.md` e `../../eks/providers/bootstrap-iam-policy.json`.
- **Alvo desta referência:** perímetro completo — boundaries por conta, roles cross-account
  escopadas Hub↔projeto, Pod Identity para os workloads do cluster, RAM restrito à
  Organization, detecção sempre ligada.
- **Gap crítico já mapeado:** o bootstrap galinha-e-ovo do IAM (a automação não pode
  auto-conceder IAM) é um passo manual de admin, não automatizável — tópico 7.

## Relação com o resto do repo

- **Depende de** `../accounts/` (SSO e contas onde as identidades vivem) e serve
  `../network/` (RAM do TGW, auth de VPN) e o futuro domínio Compute (Pod Identity do EKS).
- Regra herdada do PoC (`../../CLAUDE.md`): **só ADICIONAR** recursos isolados; nunca alterar
  policy/role compartilhada de outro time. Toda policy escopa a ARNs `poc-eks-*`/`poc-idp/*`.
