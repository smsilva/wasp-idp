# `bootstrap/` — Domain: Manual Bootstrap

Índice de leitura. Convenções e regras ficam em [`CLAUDE.md`](CLAUDE.md).

## O que este domínio entrega

Passos manuais que precedem o que o Terraform consegue fazer sozinho, porque a própria automação não pode se autoconceder o privilégio que exerce (galinha-e-ovo) ou porque o recurso em questão não é gerenciado por este Terraform.

O tópico 0 é o **anterior** a tudo o mais: sair de uma conta `network` recém-criada (ver
[`accounts/03-provisioning.md`](../accounts/03-provisioning.md)) e ter uma identidade de máquina
(`crossplane-poc`) com exatamente o privilégio que ela precisa para o Crossplane começar a
provisionar rede ([`network/`](../network/)) e depois cluster ([`compute/`](../compute/)). É o "galinha-e-ovo" descrito
em [`security/04-workload-identity.md`](../security/04-workload-identity.md) e [`security/07-crossplane-map.md`](../security/07-crossplane-map.md): a
automação não pode se auto-conceder IAM, então alguém com `AdministratorAccess` faz esse
grant **uma única vez**, manualmente.

O tópico 1 é de outra natureza: na conta `cicd` (dona da célula do cluster), o Identity Center em si não é gerenciado por este Terraform — criar e atribuir um permission set continua manual, mesmo depois de o resto da infraestrutura estar de pé.

## Tópicos

| # | Arquivo | Assunto | Pilar WAF principal |
|---|---|---|---|
| 0 | [`00-crossplane-iam-user.md`](00-crossplane-iam-user.md) | Criar a IAM user `crossplane-poc`, anexar policies, gerar access key, gravar no Secrets Manager | Security ([SEC02 — Identity management](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/identity-management.html)) |
| 1 | [`01-identity-center-eks-admin.md`](01-identity-center-eks-admin.md) | Criar permission set e account assignment no Identity Center para admin do EKS por grupo (`admin_group_ids`) | Security ([SEC02](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/identity-management.html) / [SEC03](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/permissions-management.html)) |
