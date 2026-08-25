# CLAUDE.md — `bootstrap/` (Domínio: Bootstrap Manual da Conta `network`)

> Índice do domínio de **bootstrap** — o único passo imperativo e não-automatizável desta
> arquitetura de referência: dar à automação (Crossplane) uma primeira identidade na conta
> vazia. Ordem de leitura = ordem dos arquivos. Corpo genérico (placeholders `<...>`).

## O que este domínio entrega

O passo **anterior** a tudo o mais: sair de uma conta `network` recém-criada (ver
`../accounts/03-provisionamento-de-contas.md`) e ter uma identidade de máquina
(`crossplane-poc`) com exatamente o privilégio que ela precisa para o Crossplane começar a
provisionar rede (`../network/`) e depois cluster (`../compute/`). É o "galinha-e-ovo" descrito
em `../security/04-identidade-de-workload.md` e `../security/07-mapa-crossplane.md`: a
automação não pode se auto-conceder IAM, então alguém com `AdministratorAccess` faz esse
grant **uma única vez**, manualmente.

## Tópicos

| # | Arquivo | Assunto | Pilar WAF principal |
|---|---|---|---|
| 0 | [`00-iam-user-crossplane.md`](00-iam-user-crossplane.md) | Criar a IAM user `crossplane-poc`, anexar policies, gerar access key, gravar no Secrets Manager | Security ([SEC02](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/identity-management.html)) |

## Sequência de construção (conta `network` vazia → automação com credencial)

```text
① Conta `network` criada, vazia (→ ../accounts/03-provisionamento-de-contas.md)
② Admin humano (AdministratorAccess) cria a IAM user crossplane-poc
③ Anexa PowerUserAccess (managed) — cobre EC2/VPC/EKS, exclui todo o namespace IAM
④ Anexa a inline policy CrossplaneEksRoleManagement (bootstrap-iam-policy.json) — fecha o
   gap de IAM, escopada a role/poc-eks-*
⑤ Gera a access key da user
⑥ Grava a access key no Secrets Manager (poc-idp/crossplane-poc-credentials), nunca em arquivo
⑦ Crossplane (k3d) consome a credencial via aws/eks/scripts/configure-aws-creds
```

Depois deste passo, a automação tem exatamente o privilégio necessário para
`../network/` (VPC/subnets) e, mais adiante, `../compute/` (EKS + Pod Identity) — sem
precisar de novo grant manual, salvo gap descoberto em produção (documentar e reaplicar,
ver tópico 0).

## Por que isto não é uma Composition Crossplane

Ver `../security/07-mapa-crossplane.md`: **o Crossplane provisiona o IAM do que ele
gerencia, mas não o IAM que o autoriza a gerenciar.** Automatizar este passo exigiria a
própria automação já ter o privilégio que este passo concede — circular por definição.
Fica de fora do declarativo por design, não por lacuna a fechar depois.

## Relação com o resto do repo

- **Conta que hospeda este bootstrap:** `../accounts/03-provisionamento-de-contas.md` (a
  conta `network` deve existir antes).
- **Modelo de identidade e o próprio galinha-e-ovo:** `../security/04-identidade-de-workload.md`
  e `../security/07-mapa-crossplane.md` — este domínio é o passo a passo executável do que
  aqueles tópicos descrevem em teoria.
- **Policy versionada (fonte de verdade):** `../../eks/providers/bootstrap-iam-policy.json`.
- **Consumo da credencial pelo Crossplane:** `../../eks/scripts/configure-aws-creds`.
- **Contexto operacional da conta (não-genérico):** `../../CLAUDE.md`.