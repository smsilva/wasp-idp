# HANDOFF — itens concluídos

Histórico de itens removidos do `HANDOFF.md` na raiz após conclusão.

## Bootstrap IAM user `crossplane-poc` na conta `hub` (2026-08-17)

Executado o bootstrap manual descrito em `aws/docs/bootstrap/00-crossplane-iam-user.md`
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

## Hub Crossplane de pé no k3d + credencial consumida (2026-08-17)

Fluxo de bootstrap do hub concluído nos 4 passos (`aws/eks/scripts/`), tudo local no k3d
`poc-idp` (sem VPN → pull de `xpkg.*` limpo):

1. **`install-crossplane`** — cluster k3d `poc-idp` (3 servers Ready, k3s v1.31.5) +
   Crossplane 2.3.1 (deployments 1/1).
2. **`install-providers`** — 8 providers `Healthy` (5 AWS v2.5.1 + family + helm +
   kubernetes). `provider-aws-ec2`/`eks` levaram ~7 min sob pressão de apiserver (esperado
   no host de 8 cores); um `ServiceUnavailable` transitório no `providerrevision` no meio,
   benigno.
3. **`install-functions`** — 4 Composition Functions `Healthy` em ~28s (patch-and-transform
   v0.10.8, environment-configs v0.7.3, auto-ready v0.7.0, kcl v0.12.2).
4. **`configure-aws-creds`** — Secret `aws-iam-credential` + `ProviderConfig/default`
   criados; credencial recuperada inline do Secrets Manager autentica como
   `arn:aws:iam::094289743086:user/crossplane-poc` (validado com `sts get-caller-identity`).

Lacuna fechada nesta sessão: o passo 3 não existia. `install-providers` só aplicava os
`kind: Provider`; nenhum manifesto/script tratava das Composition Functions que TODAS as
Compositions em `aws/eks/resources/` exigem (`mode: Pipeline`). Criados
`aws/eks/providers/functions.yaml` (as 4 Functions, versões fixadas) e
`aws/eks/scripts/install-functions` (espelha `install-providers`). Fluxo documentado em
`aws/CLAUDE.md` (seção "Fluxo de bootstrap do hub").

Não coberto ainda: aplicar XRD/Composition/claim da `Network` — cria VPC + NAT reais
(custo), adiado pelo usuário.