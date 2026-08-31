# Provisioning Workflow (Issue #41, Second Slice)

Segunda fatia da issue #41: o workflow do GitHub Actions em si. Spec:
`docs/superpowers/specs/2026-08-31-github-actions-provisioning-workflow-design.md`. Plano
executado inline (`superpowers:executing-plans`), 10 tasks, todas concluídas em 2026-08-31:
`docs/superpowers/plans/2026-08-31-github-actions-provisioning-workflow.md`.

## Entregue

- Raiz Terraform `aws/terraform/ci/` (T0): `aws_iam_openid_connect_provider` do GitHub Actions na
  conta `cicd`, role `cicd` (trust OIDC, `sub` aceita `refs/heads/*` por enquanto — ver issue
  #48) e role `network` (trust encadeado só na `cicd`, nunca direto no GitHub). Permissões:
  `PowerUserAccess` + inline de IAM (fallback declarado, não descuido — ver issue de
  least-privilege). `terraform test` com mutação consciente, 4 `run` verdes.
- `ci/README.md` com o passo a passo de bootstrap e os gotchas descobertos.
- Os dois workflows `.github/workflows/provision-region.yml` (OIDC → `up-02-region --with-cell`
  → fecha o endpoint público sempre, `if: always()`) e `recover-lock.yml` (force-unlock manual +
  plan para revisão humana, inputs `region`/`lock_id` sem default).
- `aws/terraform/bootstrap-checklist.md`, sequência completa do zero ao primeiro
  `workflow_dispatch`.
- `variables/values.tfvars` saiu do `.gitignore` (decisão de PoC efêmera — ver issue #50 para
  reverter quando as contas deixarem de ser descartáveis).
- As 5 issues de limitações abertas e adicionadas ao board #6: #47 (role chaining trava a sessão
  em 1h), #48 (sub do trust aceita qualquer branch), #49 (endpoint público fica aberto se o job
  morrer antes do fechamento), #50 (reverter `values.tfvars` versionado), #51 (rotação do
  certificado SAML exige atualização manual do secret).

Regressão offline completa (14 raízes, incluindo a nova `ci/`) — `Success!` em todas.

## Gotcha novo: `override_resource` não propaga para recurso sob provider aliasado

Em `terraform test`, `override_resource` funcionou normalmente para recursos sob o provider
`aws` default, mas não propagou o atributo fixado para consumidores de um recurso declarado com
`provider = aws.network` (a role `network` desta raiz) — nem sob `command = plan` nem sob
`command = apply`, testado nas duas formas. Contorno usado no run
`cicd_pode_assumir_a_role_network` (`tests/roles.tftest.hcl`): comparar a referência
(`aws_iam_role_policy.cicd_assume_network.policy`'s `Resource` field `==`
`aws_iam_role.network.arn`) em vez de conteúdo/substring — os dois leem o mesmo atributo
computado do mock, então são iguais mesmo sendo um valor sintético, provando a referência sem
depender do override. Documentado em `aws/terraform/ci/README.md`.

## Validação real: raiz `ci/` aplicada e `workflow_dispatch` de ponta a ponta

Concluída em 2026-08-31. Narrativa completa (as 8 execuções, uma por causa raiz corrigida) em
`real-run-validation.md`. Fecha a #41 e a #47.
