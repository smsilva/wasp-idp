# HANDOFF

## Why

Exercitar a PoC AWS EKS-via-Crossplane (arquitetura de referência hub-and-spoke) na conta
AWS **pessoal** do Silvio, de forma genérica, antes de qualquer ambiente corporativo. A pasta
`aws/` foi copiada de um exemplo interno e teve **todas** as referências de projeto/organização
removidas (branding, tickets, nomes de sprint, apps não-desejados).

Abordagem de genericização (registrada em `aws/CLAUDE.md`): placeholders `<...>` para
valores por-conta/segredos; valores genéricos concretos (`platform.example.com`, `poc-eks`)
onde o token é identificador executável de YAML/Crossplane. Valores reais da conta pessoal
ficam em `CLAUDE.local.md` (gitignored), não versionados.

Rejeitado: usar `<...>` em campos executáveis (quebraria API groups do k8s); manter apêndices
`99-apendice-cit.md` (deletados — eram só valores reais internos).

## In Progress

Último passo: concluída a limpeza de `aws/` — removidas referências `ciandt`/`flow-*`,
`litellm`, tickets `FLWP-*` e códigos de história `Hxx` (substituídos pela feature que
representam). Criado `CLAUDE.local.md` com a estrutura da AWS Organization pessoal (accounts
já criadas via console). Mudanças de `aws/` estão staged.

Bootstrap manual da IAM user `crossplane-poc` executado com sucesso na conta `hub`
real (`094289743086`) — ver `docs/HANDOFF-done.md` para o registro completo. Criado
profile local `hub` em `~/.aws/config` (assume `OrganizationAccountAccessRole` a
partir do profile `personal`) para acesso administrativo à conta `hub` sem SSO
dedicado.

Hub Crossplane (k3d `poc-idp`) de pé e credenciado — ver `docs/HANDOFF-done.md`. Os 4
passos do fluxo de bootstrap concluídos: `install-crossplane` → `install-providers` (8
providers Healthy) → `install-functions` (4 Composition Functions Healthy) →
`configure-aws-creds` (credencial autentica como `user/crossplane-poc`). A lacuna das
Functions foi fechada nesta sessão: criados `aws/eks/providers/functions.yaml` +
`aws/eks/scripts/install-functions` (não existiam; `install-providers` só cobria os
`kind: Provider`).

Topologia e CIDR DECIDIDOS + implementados (2026-08-18): **conta única, sem TGW** agora
(degrau de bootstrap; migração futura a hub-spoke real é aditiva — ligar TGW+attachment —
já que só o CIDR é irreversível). **Gap 1 fechado:** CIDR parametrizado por
`spec.vpcCidrSecondOctet` na supernet **`10.0.0.0/12`** (1º spoke N=1 → `10.1.0.0/16`).
Validado offline com `crossplane render` (gotcha `%d`→`%v` resolvido). Commit `97d7fdd`.
XRD + Composition já aplicados no k3d (definições, zero recurso AWS).

Exploração Helm hooks (2026-08-18): criado chart `aws/eks/charts/platform-bootstrap` que
orquestra os XRs de `resources/` em sequência via hooks — **XR = recurso normal** (upgrade/
uninstall limpos), **Job waiter = hook** (`kubectl wait ... Ready`, bloqueia o Helm = a
barreira). Fatia atual só `Network`. Validado offline (`helm lint`, `helm template`,
`kubectl apply --dry-run=server`) — zero recurso AWS. Ordem entre múltiplos XRs (quando
somar `Cluster`) decidida depois. Ver `charts/platform-bootstrap/README.md`.

**Próximo passo imediato:** aplicar o `Network` — via `helm install pb
aws/eks/charts/platform-bootstrap -n crossplane-system` (usa o chart+hooks) OU o claim
direto `kubectl apply -f examples/current/01-network.yaml`. Qualquer um **cria VPC +
subnets + NAT reais na conta hub (custo: NAT/EIP por hora)** — primeiro provisionamento AWS
de verdade. Tudo pronto: hub credenciado, Composition validada. Só falta
o "go" para aplicar e acompanhar os 16 MRs reconciliarem (`kubectl get managed`).

Contexto para a retomada:
- Hub Crossplane (k3d) 100% pronto: 8 providers + 4 functions Healthy, ProviderConfig ok.
- Direcionamento hub-and-spoke claro nas docs (`aws/docs/network/00`,`02`,`03`); distinção
  cell-based vs. rede registrada em `00` + explorações paralelas em `aws/docs/CLAUDE.md`.
- **Extensão futura mapeada:** spokes de tamanho != `/16` exigem `function-kcl` (cálculo de
  IP); TGW/HubNetwork real é Gap 2 (ainda "futuro" no `07-mapa-crossplane.md`).

## Open Questions / Hypotheses

- ~~TGW necessário para o 1º par hub↔spoke?~~ **DECIDIDO (2026-08-18):** conta única sem
  TGW agora; migração futura aditiva. Ver "In Progress".
- ~~Supernet concreta?~~ **DECIDIDO (2026-08-18):** `10.0.0.0/12`, /16 por spoke via
  `vpcCidrSecondOctet`. Gap 1 fechado (commit `97d7fdd`).
- **Base do domínio (a decidir):** `wasp.silvios.me` está em Azure DNS; pode-se delegar
  subzona para Route53. Definir se a âncora AWS é o domínio inteiro ou uma subzona
  (ex.: `aws.wasp.silvios.me`). Enquanto não delegado, sem `<hosted-zone-id>` → fatias
  DNS/ingress/TLS (fases 88+/100+) bloqueadas; rede/EKS/Pod Identity/ESO rodam sem isso.
- **Como parametrizar** os valores hoje em `CLAUDE.local.md` (chart values? env? EnvironmentConfig?)
  — decidir depois de ter uma execução ponta a ponta.
- Estrutura de OU pessoal (Infra/Workloads→Production/Sandbox) difere da doc de accounts
  (Infra=hub + conta-por-projeto) — mapear ao parametrizar.
- Track paralelo (Azure cluster-zero + Backstage multi-tenant) permanece pausado; ver
  `docs/superpowers/plans/2026-08-07-cluster-zero-terraform.md`. Não é o foco desta retomada.

## Known Broken

1. `aws/` inteira ainda é **não-executada** além do bootstrap IAM — **intentional**: k3d,
   Crossplane, providers e network seguem não provisionados/validados contra a conta pessoal.
2. `aws/eks/apps/echo/templates/*.yaml` falham em parser YAML puro — **intentional**: são Helm
   templates (`{{ }}`).
3. `idp/app-config.production.yaml` — `guest: {}` presente — **intentional** (PoC).
4. `idp/packages/backend/src/index.ts` — `allow-all` permission policy — **intentional** (PoC).
5. `idp/packages/backend/src/googleAuthModule.ts` — `dangerouslyAllowSignInWithoutUserInCatalog:
   true` — **intentional** (PoC).

## How to Resume

```bash
cd /home/silvios/git/wasp-idp
cat CLAUDE.local.md            # valores reais da AWS Organization pessoal
cat aws/CLAUDE.md              # contexto operacional + convenção de genericização
cat aws/docs/accounts/CLAUDE.md
```

## Next Steps

- [x] ~~install-crossplane + install-providers + install-functions + configure-aws-creds~~ (feito)
- [x] ~~Parametrizar CIDR da Network (Gap 1) na supernet 10.0.0.0/12~~ (feito, commit `97d7fdd`)
- [ ] **Aplicar o claim `Network`** (`kubectl apply -f aws/eks/resources/examples/current/01-network.yaml`)
      — cria VPC `10.1.0.0/16` + 4 subnets + IGW + NAT (custo) na conta hub. Acompanhar os
      16 MRs: `kubectl get managed`. Primeiro provisionamento AWS real.
- [ ] Depois da VPC: aplicar o XR `Cluster` (EKS) — requer `EnvironmentConfig` do hub antes
      (`aws/eks/resources/environment/environmentconfig.yaml`, 1x).
- [ ] Decidir base do domínio: delegar `wasp.silvios.me` (ou subzona `aws.wasp.silvios.me`)
      de Azure DNS → Route53, e registrar a hosted zone antes das fatias DNS/ingress/TLS.
- [ ] Definir estratégia de parametrização dos valores hoje em `CLAUDE.local.md`.
- [ ] (nice-to-have) Atribuir permission set SSO (`AdministratorAccess`) à conta `hub` no
      IAM Identity Center — hoje o acesso é via switch role/named profile
      (`OrganizationAccountAccessRole`). Passo a passo em
      `aws/docs/accounts/04-acesso-cross-account.md` (seção TODO).

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.
