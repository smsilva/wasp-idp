# CLAUDE.md — `bootstrap/` (Domain: Manual Bootstrap of the `network` Account)

> Regras e convenções do domínio de **bootstrap** — o único passo imperativo e
> não-automatizável desta arquitetura de referência: dar à automação (Crossplane) uma
> primeira identidade na conta vazia. Corpo genérico (placeholders `<...>`). Índice de
> leitura em [`README.md`](README.md).

## Sequência de construção (conta `network` vazia → automação com credencial)

```text
① Conta `network` criada, vazia (→ ../accounts/03-provisioning.md)
② Admin humano (AdministratorAccess) cria a IAM user crossplane-poc
③ Anexa PowerUserAccess (managed) — cobre EC2/VPC/EKS, exclui todo o namespace IAM
④ Anexa a inline policy CrossplaneEksRoleManagement (bootstrap-iam-policy.json) — fecha o
   gap de IAM, escopada a role/poc-eks-*
⑤ Gera a access key da user
⑥ Grava a access key no Secrets Manager (poc-idp/crossplane-poc-credentials), nunca em arquivo
⑦ Crossplane (k3d) consome a credencial via aws/eks/scripts/configure-aws-creds
```

Depois deste passo, a automação tem exatamente o privilégio necessário para
[`network/`](../network/) (VPC/subnets) e, mais adiante, [`compute/`](../compute/) (EKS + Pod Identity) — sem
precisar de novo grant manual, salvo gap descoberto em produção (documentar e reaplicar,
ver tópico 0).

## Por que isto não é uma Composition Crossplane

Ver [`security/07-crossplane-map.md`](../security/07-crossplane-map.md): **o Crossplane provisiona o IAM do que ele
gerencia, mas não o IAM que o autoriza a gerenciar.** Automatizar este passo exigiria a
própria automação já ter o privilégio que este passo concede — circular por definição.
Fica de fora do declarativo por design, não por lacuna a fechar depois.

## Relação com o resto do repo

- **Conta que hospeda este bootstrap:** [`accounts/03-provisioning.md`](../accounts/03-provisioning.md) (a
  conta `network` deve existir antes).
- **Modelo de identidade e o próprio galinha-e-ovo:** [`security/04-workload-identity.md`](../security/04-workload-identity.md)
  e [`security/07-crossplane-map.md`](../security/07-crossplane-map.md) — este domínio é o passo a passo executável do que
  aqueles tópicos descrevem em teoria.
- **Policy versionada (fonte de verdade):** [`eks/providers/bootstrap-iam-policy.json`](../../eks/providers/bootstrap-iam-policy.json).
- **Consumo da credencial pelo Crossplane:** [`eks/scripts/configure-aws-creds`](../../eks/scripts/configure-aws-creds).
- **Contexto operacional da conta (não-genérico):** [`CLAUDE.md`](../../CLAUDE.md).