# HANDOFF

## Why

Exercitar a PoC AWS EKS-via-Crossplane (arquitetura de referência hub-and-spoke) na conta
AWS pessoal do Silvio, genérica, antes de qualquer ambiente corporativo. `aws/` foi copiada
de um exemplo interno e genericizada (placeholders `<...>` para valores por-conta/segredos;
valores genéricos concretos como `platform.example.com`/`poc-eks` onde o token é YAML/
Crossplane executável). Valores reais ficam em `CLAUDE.local.md` (gitignored).

Topologia decidida: **conta única no bootstrap → hub-and-spoke real via cross-account**. O
Crossplane roda no **Control Plane** (k3d) autenticando como o IAM user da conta `network`, e
provisiona VPC+EKS numa conta **spoke** (não na `network`, que é só rede/conectividade) via
ProviderConfig com `assumeRoleChain`. TGW real adiado (Gap 2 — migração futura aditiva).
Rejeitado: TGW agora; CIDR fixo; `<...>` em campos executáveis.

## Vocabulário (ler antes de qualquer coisa)

"hub" cobria três eixos independentes e a ambiguidade custou tempo. Dois foram renomeados;
só o topológico mantém o termo:

| Eixo | Nome correto | Nome antigo |
|---|---|---|
| **Conta AWS** de conectividade | `network` — Connectivity Account, OU `Infrastructure` | "conta hub", profile `hub`, ProviderConfig `hub` |
| **Papel topológico** de rede | `hub` — único uso legítimo. Par de `spoke`; chart `platform/charts/hub`, VPC hub, TGW | (inalterado) |
| **Control plane** Crossplane (k3d) | **Control Plane** / `control-plane` | "hub k3d", `poc-eks-hub-config` |

`network` é canônico no whitepaper *Organizing Your AWS Environment Using Multiple Accounts*,
no AWS SRA e no Landing Zone Accelerator. A AWS **não** nomeia contas como "Hub".

O chart `platform/charts/hub` **não** foi renomeado de propósito: ali "hub" é topologia, e
`network` colidiria com o XR `Network` que ele renderiza. Chart `hub` → conta `network`.

O prefixo `poc-idp/` no Secrets Manager (`poc-idp/crossplane-poc-credentials`) é o nome real
de um secret na AWS, não apelido do cluster — **não renomear**.

## In Progress

### Frente A — bootstrap de contas / Organization

Objetivo: percorrer a sequência de provisionamento passo a passo, corrigindo doc e scripts
contra o whitepaper AWS conforme cada passo é executado de verdade. **Regra adotada: sempre
manter o vocabulário de "Organizing Your AWS Environment Using Multiple Accounts"; divergir só
com motivo registrado.**

Estado real da Organization `o-e4r8ndteju` (management `221047292361`), inspecionado na API:

```
Root  r-f11d
├── ACC  Silvio Silva          221047292361   smsilva@gmail.com          (management)
├── OU   Security              ou-f11d-ig5lcrlr
│   └── ACC  log-archive       995122007318   smsilva+log-archive@gmail.com
├── OU   Infrastructure        ou-f11d-8l7pbxgp
│   └── ACC  Network           094289743086   smsilva+network@gmail.com
└── OU   Workloads             ou-f11d-j7fnwqmx
    ├── OU   NonProd           ou-f11d-7nadx2es
    │   └── ACC  wasp-nonprod  832721568602   smsilva+wasp-nonprod@gmail.com
    └── OU   Production        ou-f11d-vyxw3s7r   (vazia)
```

**Passos ①–⑥ concluídos.** SCPs baseline verificadas em todos os targets:

| Target | SCPs (além de `FullAWSAccess`) |
|---|---|
| Root `r-f11d` | `DenyLeaveOrganization`, `ProtectCloudTrail` |
| `Security` `ou-f11d-ig5lcrlr` | `DenyOutsideApprovedRegions`, `RequireImdsv2`, `DenyRootUser` |
| `Infrastructure` `ou-f11d-8l7pbxgp` | idem |
| `Workloads` `ou-f11d-j7fnwqmx` | idem (herdado por `NonProd`/`Production`) |

Região aprovada: `us-east-1`. CloudTrail organizacional `organization-trail` (multi-region,
log file validation) + bucket `cloudtrail-o-e4r8ndteju` na `log-archive` (BPA, versionamento,
SSE-S3, `BucketOwnerEnforced`, deny non-TLS). Custo estimado **< US$ 1/mês**.

**Passo ⑦ parcial.** Identity Center `ssoins-7223e082d350408a` / identity store `d-906609a243`:

```
Silvio Silva (221047292361)   AdministratorAccess  usuário silvios     <- deveria ser grupo
log-archive  (995122007318)   ReadOnlyAccess       grupo platform-admins
Network      (094289743086)   (nenhuma — só OrganizationAccountAccessRole)
wasp-nonprod (832721568602)   (nenhuma — idem)
```

Revisão do passo ⑦ contra o WAF nesta sessão: IDs de best practice corrigidos ([SEC02-BP04](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_identities_identity_provider.html) e
[SEC03-BP02](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_permissions_least_privileges.html) estavam citados como BP01), e **break-glass ([SEC03-BP03](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_permissions_emergency_process.html)) documentado** em
`aws/docs/accounts/04-acesso-cross-account.md` — não existia processo, então o caminho real de
emergência era o root, exatamente o que ⑦ existe para evitar.

E-mail do root da `Network` migrado de `+hub@` para `+network@` (fluxo de root no console —
**não existe API** para isso; `put-account-name` muda só o nome).

Próximo passo pretendido: atribuir permission set a `Network` e `wasp-nonprod`, eliminando o
switch-role via `OrganizationAccountAccessRole`; e migrar a management account de usuário para
o grupo `platform-admins`.

### Frente B — Crossplane / EKS

Cross-account + Fase 4 (split de charts + identidade) prontos e validados offline:

- **ProviderConfigs por conta:** `network` (credencial direta, `provider-config-network.yaml`,
  aplicado por `configure-aws-creds`) e `wasp-nonprod` (assumeRoleChain,
  `provider-config-wasp-nonprod.yaml` com `${SPOKE_ACCOUNT_ID}` via envsubst, aplicado por
  `configure-account-access`). Sem PC `default` — falha-fechado.
- **Role `crossplane-wasp-nonprod`** na conta `832721568602`: trust p/ `crossplane-poc` da
  `Network` + PowerUserAccess + inline `CrossplaneEksRoleManagement`. Assume validado com as
  creds reais do `crossplane-poc`. Substituiu `crossplane-sandbox` (recriada — IAM não
  renomeia in-place; a antiga foi removida).
- **Identidade = `metadata.name`** (Crossplane v2, sem `spec.id`): external-names e label `env`
  derivam dele. Spoke e cluster compartilham o `metadata.name`. `providerConfigName`
  OBRIGATÓRIO, enum `[network, wasp-nonprod]`.
- **Charts `aws/platform/charts/{hub,spoke,cluster}`**: um release por célula. Helper
  `aws/eks/scripts/random-id` (5 chars).
- **Control Plane renomeado:** default `--cluster-name` = `control-plane` (contexto
  `k3d-control-plane`) em 8 scripts; `EnvironmentConfig` `control-plane-config` com label
  `platform.example.com/control-plane`.

Identidade da credencial-raiz analisada vs. Well-Architected (registro em
`aws/docs/security/04-identidade-de-workload.md`): cross-account `network`→spoke
(`AssumeRole`+STS) já é WAF-aligned; o único cheiro é o **access key de longa duração** do
`crossplane-poc`, porque o Crossplane roda num k3d fora da AWS. **Decisão (PoC): aceito como
débito consciente** — resolve-se ao migrar o Control Plane p/ AKS (OIDC federation,
`AssumeRoleWithWebIdentity`) ou EKS (IRSA); Roles Anywhere é o plano B p/ eliminar o key ainda
no k3d.

O ciclo real já foi provado antes do rename (com o chart antigo): `helm install` criou VPC
`10.1.0.0/16`+NAT, `helm uninstall` destruiu tudo (teardown limpo AWS-side). Orquestrador
`environment/` marcado BLOCKED (incompatível com `metadata.name`; rework = sketches
`resources/examples/topology/05-07`).

**Custo atual: zero.** O Control Plane k3d foi destruído (chamava-se `flow-idp`, criado com
`--cluster-name` custom; tinha os 8 providers `Healthy` e **zero managed resources**, então
não há recurso AWS órfão). Nenhuma VPC/EKS de pé.

**Cadeia renomeada validada ponta a ponta (2026-08-24), custo zero.** Control Plane recriado do
zero: 8 providers `Healthy`, 4 functions `Healthy`, XRDs `network`/`cluster` `Established`,
ProviderConfigs `network`+`wasp-nonprod` sem resíduo de nome antigo. As 4 checagens do "How to
Resume" passaram.

**Achado durante a validação:** `install-crossplane` nascia com `--servers 3` (default herdado
do track Azure, que só documentava lentidão) e neste host (8 cores) isso quebrava o **quorum do
etcd** — crash-loop persistente, não simples atraso. Fix: recriar com `--servers 1`; providers
ficaram `Healthy` em ~4 min sem restart. Default do script alterado para 1. Ver
`aws/CLAUDE.md`, "Gotcha (RESOLVIDA): k3d com 3 servers quebra o quorum do etcd neste host".

Próximo passo pretendido: **Fase 5** — aplicar os charts `hub` → `spoke` → `cluster` (custo
alto, VPC+EKS reais numa conta spoke). Control Plane atual já está pronto para isso; não
precisa recriar.

## Open Questions / Hypotheses

- **Cadeia renomeada nunca rodou contra um cluster real.** Validada só por `helm template`,
  `bash -n`, lint de YAML/JSON e leitura do enum do schema. Suspeita a confirmar no
  bootstrap: `configure-aws-creds` aplica `provider-config-network.yaml` e
  `configure-account-access --name wasp-nonprod` resolve o `${SPOKE_ACCOUNT_ID}` sem
  resíduo do nome antigo.
- **Renomear o cluster k3d muda o contexto de tudo** (`k3d-control-plane`). Se algum script
  ou doc ainda assumir `k3d-poc-idp`, só aparece em runtime.
- **Base do domínio:** `wasp.silvios.me` em Azure DNS; delegar subzona (ex.:
  `aws.wasp.silvios.me`) para Route53 ou o domínio inteiro? Sem `<hosted-zone-id>` as fatias
  DNS/ingress/TLS ficam bloqueadas; rede/EKS/Pod Identity/ESO rodam sem isso.
- **Parametrizar** valores de `CLAUDE.local.md` (chart values? env? EnvironmentConfig?) —
  decidir após execução ponta a ponta.
- **Rework do orquestrador `environment/`** (BLOCKED): sob `metadata.name`, filhos compostos
  ganham nome hasheado → o cruzamento por label compartilhado não funciona no orquestrador.
  Conserto desenhado em `resources/examples/topology/05-07` (injetar `subnetIds` do
  `Network.status` no Cluster em vez de casar por label; exige `function-kcl` ou Network
  publicar arrays). Adiado — os charts diretos não dependem dele.
- **Retenção do bucket de auditoria** (lifecycle → Glacier após N dias, expiração após M
  anos): decisão de compliance, deliberadamente adiada. É o único custo do CloudTrail que
  cresce sozinho e para sempre.
- **Conta `security-tooling`** desenhada como slot, não criada — vira pré-requisito quando
  GuardDuty/Config/Security Hub entrarem.
- **`Sandbox` como conceito** fica reservado para outra coisa (conta de brincar, desconectada
  da rede, sem attachment no TGW) — não é o ambiente de teste do projeto, que é
  `<projeto>-nonprod`.
- Track paralelo (Azure cluster-zero + Backstage multi-tenant) pausado; não é o foco.

## Known Broken

1. **Break-glass documentado, controles ausentes** — *unexpected*: MFA no root da management
   account e das contas-membro **não verificado**; alarme de uso de root **não existe**
   (CloudTrail já captura, falta a regra EventBridge); ensaio nunca executado. Ver
   `aws/docs/accounts/CLAUDE.md`, decisões em aberto 4 e 5.
2. **Management account com `AdministratorAccess` atribuído a usuário, não a grupo** —
   *unexpected*: viola a própria regra `--group` da doc, na conta mais privilegiada. Migrar
   para `platform-admins` (atribuir o grupo antes de revogar o usuário).
3. VPC+EKS ainda NÃO provisionados numa spoke — *intentional*: custo alto, só sob autorização
   explícita.
4. `crossplane render` não injeta defaults do XRD — *intentional* (limitação da ferramenta):
   passar `providerConfigName`/`metadata.name` explícitos no XR de teste. `providerConfigName`
   é OBRIGATÓRIO (sem default): XR sem ele é rejeitado, não há fallback.
5. `enum` de `providerConfigName` inclui `wasp-nonprod` (nome específico da conta) nos XRDs
   versionados — *intentional*: trade-off aceito vs. genericização; comentário instrui
   ajustar a lista `[network, wasp-nonprod]` por instância.
6. `aws/eks/apps/echo/templates/*.yaml` falham em parser YAML puro — *intentional*: Helm
   templates (`{{ }}`).
7. `revoke-permission-set` só foi exercido no caminho feliz (revogação real da
   `log-archive`); os ramos "atribuição inexistente" e "permission set inexistente" nunca
   rodaram.
8. `idp/app-config.production.yaml` `guest: {}`; `idp/packages/backend/src/index.ts`
   `allow-all` policy; `idp/packages/backend/src/googleAuthModule.ts`
   `dangerouslyAllowSignInWithoutUserInCatalog: true` — *intentional* (PoC).

## How to Resume

**Objetivo desta retomada: Fase 5 — aplicar os charts `hub`→`spoke`→`cluster`.** O Control
Plane já está de pé e validado (ver "Frente B" acima); não precisa recriar. A partir daqui
os `helm install` **cobram** (VPC+NAT no `spoke`, EKS+nodegroup no `cluster`).

Pré-requisito: VPN corporativa **desconectada** e SSO admin ativo
(`aws sso login --profile personal`). Se o Control Plane tiver sido destruído desde a última
sessão, recriar primeiro:

```bash
cd /home/silvios/git/wasp-idp
k3d cluster list                       # confirmar estado antes de assumir

aws/eks/scripts/install-crossplane     # cria k3d "control-plane" (1 server) + Crossplane
aws/eks/scripts/install-providers --timeout 900s
aws/eks/scripts/install-functions      # OBRIGATÓRIO: toda Composition é mode: Pipeline

# credencial do crossplane-poc inline do Secrets Manager (nunca persistir em arquivo):
set -a; source <(AWS_PROFILE=network aws secretsmanager get-secret-value \
  --secret-id poc-idp/crossplane-poc-credentials --region us-east-1 \
  --query SecretString --output text \
  | jq -r '"AWS_ACCESS_KEY_ID=" + .aws_access_key_id, "AWS_SECRET_ACCESS_KEY=" + .aws_secret_access_key'); set +a
aws/eks/scripts/configure-aws-creds    # Secret aws-iam-credential + ProviderConfig "network"
aws/eks/scripts/configure-account-access --name wasp-nonprod --account-id 832721568602

kubectl apply -f aws/eks/resources/network/{xrd,composition}.yaml
kubectl apply -f aws/eks/resources/cluster/{xrd,composition}.yaml
```

**Gotcha:** `install-crossplane` default é `--servers 1` (mudado nesta sessão — 3 servers
quebrou o quorum do etcd neste host, ver `aws/CLAUDE.md`). Não usar `--servers 3` sem motivo.

Checagens que provam o rename (já passaram nesta sessão, repetir só se recriar do zero):

```bash
kubectl config current-context                                    # k3d-control-plane
kubectl get providerconfig.aws.upbound.io                          # network + wasp-nonprod, sem "hub"/"sandbox"/"default"
kubectl get xrd networks.platform.example.com -o jsonpath='{.spec.versions[0].schema.openAPIV3Schema.properties.spec.properties.providerConfigName.enum}'
helm template hub-us-east-1 aws/platform/charts/hub --set name=hub-us-east-1 | grep providerConfigName
```

Perfis locais: `network` (`094289743086`) e `wasp-nonprod` (`832721568602`), ambos assumindo
`OrganizationAccountAccessRole` a partir de `personal`. Backup do `~/.aws/config` antes do
rename dos profiles: `~/.aws/config.bak-20260824`.

Ordem dos charts controla o custo (só `cluster` cobra alto):

```bash
helm install hub-us-east-1 aws/platform/charts/hub -n crossplane-system --set name=hub-us-east-1
ID=$(aws/eks/scripts/random-id)
helm install spoke-$ID aws/platform/charts/spoke -n crossplane-system --set name=$ID
# cluster: CUSTO ALTO (~30 min, NAT + control plane ~US$0,10/h + 3x t3.medium)
helm install cluster-$ID aws/platform/charts/cluster -n crossplane-system --set name=$ID \
  --set providerConfigName=wasp-nonprod \
  --set crossplaneArn=arn:aws:iam::832721568602:role/crossplane-wasp-nonprod
```

A role `crossplane-wasp-nonprod` e o secret do `crossplane-poc` **persistem** na AWS (não
dependem do k3d) — não precisam re-bootstrap. `provision-eks`/`teardown` longos: rodar em
background, com as creds carregadas inline no mesmo shell.

## Next Steps

### Frente A — contas

- [x] Vocabulário do whitepaper aplicado em doc, scripts e na Organization real.
- [x] CloudTrail organizacional + conta `log-archive` + bucket de auditoria.
- [x] **Passo ⑥ — SCPs baseline** em Root/Security/Infrastructure/Workloads (`us-east-1`).
      SCP **não** afeta a management account.
- [x] Permission set de rotina da `log-archive` em `ReadOnlyAccess`.
- [x] E-mail do root da `Network` alinhado (`+hub@` → `+network@`).
- [x] Break-glass ([SEC03-BP03](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_permissions_emergency_process.html)) documentado; IDs do WAF conferidos contra as páginas oficiais.
- [ ] Atribuir permission set a `Network` e `wasp-nonprod`
      (`./assign-permission-set --account <conta> --group platform-admins`) — elimina o
      switch-role via `OrganizationAccountAccessRole`.
- [ ] Migrar a atribuição da management account de usuário `silvios` para grupo
      `platform-admins` (atribuir o grupo **antes** de revogar o usuário).
- [ ] Verificar/habilitar MFA no root da management account e das contas-membro.
- [ ] Criar a regra de alarme de uso de root (CloudTrail → EventBridge → notificação).
- [ ] Decidir retenção/lifecycle do bucket `cloudtrail-o-e4r8ndteju`.

### Frente B — Crossplane / EKS

- [x] **Fase 4:** split de charts + identidade `metadata.name` + PCs por conta.
- [x] Vocabulário alinhado: conta `network`, conta `wasp-nonprod`, Control Plane; role IAM
      recriada como `crossplane-wasp-nonprod`.
- [x] **Validar a cadeia renomeada** recriando o Control Plane do zero (2026-08-24). Custo
      zero. Achado: `--servers 3` quebrava o quorum do etcd neste host — default mudado
      para 1 em `install-crossplane`.
- [ ] **Fase 5:** aplicar `hub` → `spoke` (`10.2`, `wasp-nonprod`) → esperar Ready →
      `cluster` (EKS). Custo alto. Acompanhar: `kubectl get managed`. É o próximo passo.
- [ ] Decidir base do domínio (delegar `wasp.silvios.me`/subzona → Route53) antes das fatias
      DNS/ingress/TLS.
- [ ] Definir estratégia de parametrização dos valores de `CLAUDE.local.md`.

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.
