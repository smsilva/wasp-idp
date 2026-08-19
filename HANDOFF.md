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

Cross-account + Fase 4 (split de charts + identidade) prontos. Feito e validado:
- Role `crossplane-sandbox` na conta sandbox (`832721568602`): trust p/ `crossplane-poc` da
  hub + PowerUserAccess + inline IAM. AssumeRole cross-account testado (funciona).
- **ProviderConfigs por conta:** `hub` (`provider-config-hub.yaml`) + `sandbox`
  (`provider-config-sandbox.yaml`, `${SPOKE_ACCOUNT_ID}` via envsubst, aplicado por
  `configure-account-access`). Sem PC `default` (falha-fechado).
- **Identidade migrada `spec.id` → `metadata.name`** (Crossplane v2): XRDs `Network`/`Cluster`
  não têm mais `id`; external-names e label `env` derivam de `metadata.name`. Spoke e cluster
  compartilham o `metadata.name`. `providerConfigName` OBRIGATÓRIO, enum `[hub, sandbox]`.
- **Charts `aws/platform/charts/{hub,spoke,cluster}`** (substituem `platform-bootstrap`): um
  release por célula, keados em `metadata.name`. Helper `aws/eks/scripts/random-id` (5 chars).
- Validado por `crossplane render`: Network 16/16 MRs `providerConfigRef: sandbox` + label
  `env=<name>` + `tags.Name: poc-eks-<name>-*`; Cluster 11/11 MRs sandbox + external-names +
  `crossplaneArn` (role da sandbox) no AccessEntry/APA. `helm template`/`lint` OK nos 3 charts.

Identidade da credencial-raiz analisada vs. Well-Architected (registro em
`aws/docs/security/04-identidade-de-workload.md`): cross-account hub→spoke (`AssumeRole`+STS)
já é WAF-aligned; o único cheiro é o **access key de longa duração** da hub (`crossplane-poc`),
porque o Crossplane roda num k3d fora da AWS. **Decisão (PoC): Tema 1 aceito como débito
consciente** — resolve-se ao migrar o control plane p/ AKS (OIDC federation,
`AssumeRoleWithWebIdentity`) ou EKS (IRSA); Roles Anywhere seria o plano B p/ eliminar o key
ainda no k3d. Seguimos para a Fase 4.

O ciclo real já foi provado antes (com o chart antigo): `helm install` criou VPC `10.1.0.0/16`
+NAT na hub, `helm uninstall` destruiu tudo (teardown limpo AWS-side). Orquestrador
`environment/` marcado BLOCKED (incompatível com metadata.name; rework = sketches
`resources/examples/topology/05-07`). Custo atual: **zero** (k3d destruído, nenhuma VPC/EKS).

Próximo passo pretendido: **Fase 5 — aplicar hub + spoke + cluster de verdade** na sandbox
(custo alto). Só código até aqui.

## Open Questions / Hypotheses

- **Fase 4 — RESOLVIDA:** Opção B (charts separados). `aws/platform/charts/{hub,spoke,cluster}`,
  1 release por célula, keados em `metadata.name`. Endereçamento: hub=`10.1.0.0/16` (N=1),
  spoke sandbox=`10.2.0.0/16` (N=2).
- **Rework do orquestrador `environment/`** (BLOCKED): sob `metadata.name`, filhos compostos
  ganham nome hasheado → o cruzamento por label compartilhado não funciona no orquestrador.
  Conserto desenhado em `resources/examples/topology/05-07` (injetar `subnetIds` do
  `Network.status` no Cluster em vez de casar por label; exige `function-kcl` ou Network
  publicar arrays). Adiado — os charts diretos não dependem dele.
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
2. `crossplane render` não injeta defaults do XRD — *intentional* (limitação da ferramenta):
   passar `providerConfigName`/`metadata.name` explícitos no XR de teste. `providerConfigName`
   agora é OBRIGATÓRIO (sem default): não há mais fallback implícito — XR sem ele é rejeitado
   (falha-fechado).
3. `enum` de `providerConfigName` inclui `sandbox` (nome específico da conta) nos XRDs
   versionados — *intentional*: trade-off aceito vs. genericização; comentário instrui
   ajustar a lista `[hub, sandbox]` por instância.
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
aws/eks/scripts/configure-aws-creds                 # Secret + ProviderConfig hub
# ProviderConfig cross-account sandbox (account-id via CLAUDE.local.md):
aws/eks/scripts/configure-account-access --name sandbox --account-id 832721568602
# XRDs + Compositions:
kubectl apply -f aws/eks/resources/network/{xrd,composition}.yaml
kubectl apply -f aws/eks/resources/cluster/{xrd,composition}.yaml
cat CLAUDE.local.md                                 # valores reais + role crossplane-sandbox
```

Depois, os charts (custo controlado pela ordem — só o `cluster` cobra alto):
```bash
helm install hub-us-east-1 aws/platform/charts/hub -n crossplane-system --set name=hub-us-east-1
ID=$(aws/eks/scripts/random-id)
helm install spoke-$ID aws/platform/charts/spoke -n crossplane-system --set name=$ID
# cluster: CUSTO ALTO (~30 min). crossplaneArn = role da conta sandbox.
helm install cluster-$ID aws/platform/charts/cluster -n crossplane-system --set name=$ID \
  --set providerConfigName=sandbox \
  --set crossplaneArn=arn:aws:iam::832721568602:role/crossplane-sandbox
```

A role `crossplane-sandbox` e o secret `crossplane-poc` na AWS **persistem** (não dependem
do k3d) — não precisam re-bootstrap.

## Next Steps

- [x] **Fase 4:** split de charts (Opção B) + migração de identidade `metadata.name` + PCs
      `hub`/`sandbox`. Validado offline (`helm template`/`lint` + `crossplane render`).
- [ ] **Fase 5:** subir k3d + bootstrap (How to Resume) e aplicar `hub` → `spoke` (`10.2`,
      sandbox) → esperar Ready → `cluster` (EKS). Custo alto (NAT + control plane ~US$0,10/h +
      3× t3.medium). `crossplaneArn=arn:aws:iam::832721568602:role/crossplane-sandbox` (role da
      sandbox, não user da hub). Acompanhar: `kubectl get managed`.
- [ ] Decidir base do domínio (delegar `wasp.silvios.me`/subzona → Route53) antes das fatias
      DNS/ingress/TLS.
- [ ] Definir estratégia de parametrização dos valores de `CLAUDE.local.md`.
- [ ] (nice-to-have) Permission set SSO (`AdministratorAccess`) para hub/sandbox no IAM
      Identity Center — hoje acesso via named profile (`OrganizationAccountAccessRole`).
      Passo a passo em `aws/docs/accounts/04-acesso-cross-account.md`.

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.
