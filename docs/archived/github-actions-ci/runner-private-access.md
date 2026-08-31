# Runner Private Access (PR #46)

Primeira fatia da issue #41: o mecanismo de acesso privado do runner do GitHub Actions.

Flags `--public-cidr`/`--close-public-access` acrescentadas a `up-02-region`, fechando o wiring
gap de `endpoint_public_access`/`public_access_cidrs` que nunca chegava a `module.cell` desde a
[ADR 0014](../../adr/0014-single-regional-root-composing-hub-and-cell-modules.md). Desenho em
`docs/superpowers/specs/2026-08-31-github-actions-runner-private-access-design.md` e plano
correspondente (todos os checkboxes marcados). PR #46 mergeada em 2026-08-31.

## Step 10 rodado de verdade contra `regions/us-east-1`

O `plan` mostrou `endpoint_public_access = true` e `public_access_cidrs = ["203.0.113.10/32"]` em
`module.cell.module.cluster.aws_eks_cluster.this` (120 to add, 0 erros — região com zero
recursos). Exigiu recriar `variables/values.tfvars` (não existia neste checkout; valores
redescobertos via `aws organizations list-accounts`/`sso-admin list-instances`/`identitystore
list-groups` + `az network dns zone list`, ver `variables/values.tfvars.example` para o que cada
chave significa) e baixar `variables/saml-metadata.xml` real do console do Identity Center (passo
de console documentado em
`docs/superpowers/plans/2026-08-26-private-access-and-ingress/02-private-access.md`, seção "O
passo de console, clique a clique" — não está no `README.md`, só uma referência de rodapé lá).

## Achado no caminho: lock órfão

O `plan` falhou na primeira tentativa com `Error acquiring the state lock` — lock de
`regions/us-east-1` órfão de uma sessão anterior, criado ~1h20 antes e nunca liberado. Resolvido
com `terraform force-unlock` depois de confirmar (com o operador) que não havia `apply`/`plan`
ativo em outro lugar. Lição para a próxima vez que isso ocorrer: sempre confirmar com o operador
antes de forçar — nunca assumir órfão só pela idade do lock.
