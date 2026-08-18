# HANDOFF

## Why

Exercitar a PoC AWS EKS-via-Crossplane (arquitetura de referência hub-and-spoke) na conta
AWS pessoal do Silvio, genérica, antes de qualquer ambiente corporativo. `aws/` foi copiada
de um exemplo interno e genericizada (placeholders `<...>` para valores por-conta/segredos;
valores genéricos concretos como `platform.example.com`/`poc-eks` onde o token é YAML/
Crossplane executável). Valores reais ficam em `CLAUDE.local.md` (gitignored).

Topologia decidida: **conta única no bootstrap → hub-and-spoke real via cross-account**. O
Crossplane roda na conta hub e provisiona VPC+EKS numa conta **spoke** (não na hub, que é só
rede/conectividade) via ProviderConfig com `assumeRoleChain`. TGW real adiado (Gap 2 —
migração futura aditiva). Rejeitado: TGW agora; CIDR fixo; `<...>` em campos executáveis.

## In Progress

Cross-account preparado (Fases 1-3 de 5). Feito e validado:
- Role `crossplane-sandbox` na conta sandbox (`832721568602`): trust p/ `crossplane-poc` da
  hub + PowerUserAccess + inline IAM. AssumeRole cross-account testado (funciona).
- ProviderConfig `spoke-sandbox` (`assumeRoleChain`) aplicado no k3d, ao lado do `default`.
- XRDs/Compositions `Network`+`Cluster` parametrizados com `spec.providerConfigName` (enum
  `[default, spoke-sandbox]`); patchSet `provider-config` nos MRs AWS (16 Network / 11
  Cluster); ProviderConfigs remotos helm/k8s NÃO recebem. Validado por `crossplane render`.

Chart `aws/eks/charts/platform-bootstrap` tem grupos 100 (Network) e 200 (Cluster,
`cluster.enabled:false`). Já provou o ciclo real: `helm install` criou VPC `10.1.0.0/16`+NAT
na hub, `helm uninstall` destruiu tudo (teardown limpo confirmado AWS-side). Custo atual: **zero**.

Próximo passo pretendido: **Fase 4 — modelar hub+spokes no chart** (decisão adiada, ver
Open Questions), depois **Fase 5 — aplicar Network spoke + EKS na sandbox** (custo alto).

## Open Questions / Hypotheses

- **Fase 4 — como o chart modela hub + N spokes** (hoje 1 release = 1 Network). Opção A:
  `values.environments: [...]` com `range` (1 release gerencia tudo, reescreve templates).
  Opção B (recomendada): 1 release por ambiente — `pb-hub` (Network/`default`) + `pb-sbx01`
  (Network+Cluster/`spoke-sandbox`); `id`/`providerConfigName`/CIDR já são values, uninstall
  isola por spoke. Endereçamento fixado: hub=`10.1.0.0/16` (N=1), spoke sandbox=`10.2.0.0/16`
  (N=2).
- **Base do domínio:** `wasp.silvios.me` em Azure DNS; delegar subzona (ex.:
  `aws.wasp.silvios.me`) para Route53 ou o domínio inteiro? Sem `<hosted-zone-id>` as fatias
  DNS/ingress/TLS ficam bloqueadas; rede/EKS/Pod Identity/ESO rodam sem isso.
- **Parametrizar** valores de `CLAUDE.local.md` (chart values? env? EnvironmentConfig?) —
  decidir após execução ponta a ponta.
- Estrutura de OU pessoal (Infra/Workloads→Production/Sandbox) difere da doc de accounts
  (Infra=hub + conta-por-projeto) — mapear ao parametrizar.
- Track paralelo (Azure cluster-zero + Backstage multi-tenant) pausado; não é o foco.

## Known Broken

1. VPC+EKS ainda NÃO provisionados numa spoke — *intentional*: Fases 4-5 pendentes, custo
   alto só sob autorização. Cross-account (Fases 1-3) pronto e validado offline.
2. `crossplane render` não injeta defaults do XRD (campo omitido no claim fica vazio) —
   *intentional* (limitação da ferramenta): o default só é aplicado server-side; MR sem
   providerConfigRef cai no `default` implícito (seguro, hub).
3. `enum` de `providerConfigName` inclui `spoke-sandbox` (nome específico da conta) nos XRDs
   versionados — *intentional*: trade-off aceito vs. genericização; comentário instrui
   ajustar a lista por instância.
4. `aws/eks/apps/echo/templates/*.yaml` falham em parser YAML puro — *intentional*: Helm
   templates (`{{ }}`).
5. `idp/app-config.production.yaml` `guest: {}`; `idp/packages/backend/src/index.ts`
   `allow-all` policy; `idp/packages/backend/src/googleAuthModule.ts`
   `dangerouslyAllowSignInWithoutUserInCatalog: true` — *intentional* (PoC).

## How to Resume

O cluster k3d `poc-idp` foi **destruído** (`k3d cluster delete`) — recriar do zero pelo
fluxo de bootstrap, depois reaplicar XRDs/Compositions/ProviderConfig cross-account:

```bash
cd /home/silvios/git/wasp-idp
aws/eks/scripts/install-crossplane
aws/eks/scripts/install-providers --timeout 900s
aws/eks/scripts/install-functions
# credencial crossplane-poc inline do Secrets Manager -> configure-aws-creds:
set -a; source <(AWS_PROFILE=hub aws secretsmanager get-secret-value \
  --secret-id poc-idp/crossplane-poc-credentials --region us-east-1 \
  --query SecretString --output text \
  | jq -r '"AWS_ACCESS_KEY_ID=" + .aws_access_key_id, "AWS_SECRET_ACCESS_KEY=" + .aws_secret_access_key'); set +a
aws/eks/scripts/configure-aws-creds
# cross-account + XRs:
kubectl apply -f aws/eks/providers/provider-config-spoke-sandbox.yaml
kubectl apply -f aws/eks/resources/network/{xrd,composition}.yaml
kubectl apply -f aws/eks/resources/cluster/{xrd,composition}.yaml
cat CLAUDE.local.md                                 # valores reais + role crossplane-sandbox
```

A role `crossplane-sandbox` e o secret `crossplane-poc` na AWS **persistem** (não dependem
do k3d) — não precisam re-bootstrap.

## Next Steps

- [ ] **Fase 4:** decidir modelagem hub+spokes no chart (Opção B recomendada) e ajustar
      `platform-bootstrap` (`values`: hub sem cluster / spoke com `providerConfigName:
      spoke-sandbox`, `vpcCidrSecondOctet: 2`, `cluster.enabled: true`).
- [ ] **Fase 5:** aplicar Network spoke (`10.2`, sandbox) → esperar Ready → aplicar Cluster
      (EKS). Custo alto (NAT + control plane ~US$0,10/h + 3× t3.medium). Passar
      `cluster.crossplaneArn=arn:aws:iam::832721568602:...` ou o da hub conforme a conta que
      dá admin no EKS. Acompanhar: `kubectl get managed`.
- [ ] Decidir base do domínio (delegar `wasp.silvios.me`/subzona → Route53) antes das fatias
      DNS/ingress/TLS.
- [ ] Definir estratégia de parametrização dos valores de `CLAUDE.local.md`.
- [ ] (nice-to-have) Permission set SSO (`AdministratorAccess`) para hub/sandbox no IAM
      Identity Center — hoje acesso via named profile (`OrganizationAccountAccessRole`).
      Passo a passo em `aws/docs/accounts/04-acesso-cross-account.md`.

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.
