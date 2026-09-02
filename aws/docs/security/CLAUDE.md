# CLAUDE.md — `security/` (Domain: Security & IAM)

> Regras e convenções do domínio de **Segurança e IAM** — o perímetro de identidade e os
> controles que permeiam todos os outros domínios. Corpo genérico (placeholders `<...>`).
> Índice de leitura em [`README.md`](README.md).

## Sequência de construção (perímetro de identidade)

```text
① SSO na management account (→ ../accounts/04) — identidade humana federada, sem IAM user por conta
② Permission sets nomeados por função + permission boundaries por conta (teto de privilégio)
③ Policies escopadas por ARN para cada workload/automação (menor privilégio, não wildcard)
④ Roles cross-account com trust policy escopada (Hub↔projeto) — em vez de duplicar credenciais
⑤ RAM shares com allowExternalPrincipals=false (perímetro: só a própria Organization)
⑥ Identidade de workload no cluster (Pod Identity/IRSA) — pods assumem role, sem access key montada
  ⑥b Identidade do próprio control plane: 1 role origem por control plane regional (→ tópico 8)
⑦ Autenticação de VPN (cert/SSO para client; PSK para site-to-site) fechando no Hub
⑧ Detecção sempre ligada (CloudTrail + Access Analyzer + GuardDuty) — violação vira sinal
```

## Estado atual vs. alvo (resumo)

- **Hoje no PoC:** um IAM user dedicado (`crossplane-poc`) com `PowerUserAccess` +
  inline policy escopada às roles `poc-eks-*` opera o Crossplane; humanos entram via SSO
  `AdministratorAccess`. **Cross-account já existe:** uma role na conta de workload com trust
  para esse user, assumida via `assumeRoleChain` do ProviderConfig — o hop Hub→spoke está
  validado. Ainda sem permission boundary e sem Access Analyzer. Ver [`CLAUDE.md`](../../CLAUDE.md) e
  [`eks/providers/bootstrap-iam-policy.json`](../../eks/providers/bootstrap-iam-policy.json).
- **Alvo desta referência:** perímetro completo — boundaries por conta, roles cross-account
  escopadas Hub↔projeto, Pod Identity para os workloads do cluster, RAM restrito à
  Organization, detecção sempre ligada.
- **Gap crítico já mapeado:** o bootstrap galinha-e-ovo do IAM (a automação não pode
  auto-conceder IAM) é um passo manual de admin, não automatizável — tópico 7.
- **Gap estrutural:** a credencial-raiz ainda é uma **access key de longa duração**, o que
  contraria [SEC02-BP02 — Use temporary credentials](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_identities_unique.html).
  Aceitável para um control plane; insustentável para N control planes regionais — tópico 8.

## Relação com o resto do repo

- **Depende de** [`accounts/`](../accounts/) (SSO e contas onde as identidades vivem) e serve
  [`network/`](../network/) (RAM do TGW, auth de VPN) e o futuro domínio Compute (Pod Identity do EKS).
- Regra herdada do PoC ([`CLAUDE.md`](../../CLAUDE.md)): **só ADICIONAR** recursos isolados; nunca alterar
  policy/role compartilhada de outro time. Toda policy escopa a ARNs `poc-eks-*`/`poc-idp/*`.
