# `bootstrap/` — Domain: Manual Bootstrap of the `network` Account

Índice de leitura. Convenções e regras ficam em [`CLAUDE.md`](CLAUDE.md).

## O que este domínio entrega

O passo **anterior** a tudo o mais: sair de uma conta `network` recém-criada (ver
`../accounts/03-provisioning.md`) e ter uma identidade de máquina
(`crossplane-poc`) com exatamente o privilégio que ela precisa para o Crossplane começar a
provisionar rede (`../network/`) e depois cluster (`../compute/`). É o "galinha-e-ovo" descrito
em `../security/04-workload-identity.md` e `../security/07-crossplane-map.md`: a
automação não pode se auto-conceder IAM, então alguém com `AdministratorAccess` faz esse
grant **uma única vez**, manualmente.

## Tópicos

| # | Arquivo | Assunto | Pilar WAF principal |
|---|---|---|---|
| 0 | [`00-crossplane-iam-user.md`](00-crossplane-iam-user.md) | Criar a IAM user `crossplane-poc`, anexar policies, gerar access key, gravar no Secrets Manager | Security ([SEC02 — Identity management](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/identity-management.html)) |
