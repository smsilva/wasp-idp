# HANDOFF — itens concluídos

Histórico de itens removidos do `HANDOFF.md` na raiz após conclusão.

## Bootstrap IAM user `crossplane-poc` na conta `hub` (2026-08-17)

Executado o bootstrap manual descrito em `aws/docs/bootstrap/00-iam-user-crossplane.md`
contra a conta `hub` real (`094289743086`), usando `AWS_PROFILE=hub` (novo profile local
que assume `OrganizationAccountAccessRole` a partir do profile `personal`).

Resultado:

- IAM user `crossplane-poc` criada.
- Policy gerenciada `PowerUserAccess` anexada.
- Confirmado `implicitDeny` em `iam:CreateRole`/`GetRole`/`PutRolePolicy` só com
  `PowerUserAccess` (gap esperado, documentado no passo ③).
- Policy inline `CrossplaneEksRoleManagement` aplicada (renderizada de
  `aws/eks/providers/bootstrap-iam-policy.json` com `<account-id>` → `094289743086`,
  descartada após uso — o arquivo versionado permanece genérico).
- Access key gerada e gravada em `poc-idp/crossplane-poc-credentials` (Secrets Manager,
  `us-east-1`) — nunca persistida em arquivo local.
- Verificação final (`get-user`, `list-attached-user-policies`, `list-user-policies`,
  `describe-secret`) confere com o esperado no doc.

Não coberto ainda: passo ⑦ (consumir a credencial no Crossplane via
`aws/eks/scripts/configure-aws-creds`) — depende do k3d/Crossplane estarem instalados
(próximo item do `HANDOFF.md`).