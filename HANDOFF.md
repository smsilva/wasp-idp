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

**Próximo passo imediato:** aplicar a `Network` (XRD + Composition + claim
`examples/current/01-network.yaml`) — **cria VPC + NAT reais na conta hub (custo)**; o
usuário adiou ("não agora"). O hub já tem todos os pré-requisitos (providers + functions).
Antes de aplicar, decidir se dá para pular o NAT nesta fatia e revisar o CIDR hardcoded
(`172.16.0.0/16`, Gap 1 do `aws/docs/network/07-mapa-crossplane.md`).

## Open Questions / Hypotheses

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

- [ ] Rodar `aws/eks/scripts/install-crossplane` + `install-providers` (k3d local).
- [ ] Consumir a credencial `crossplane-poc` no cluster (passo ⑦ do bootstrap, via
      `aws/eks/scripts/configure-aws-creds`).
- [ ] Configurar **network** na `hub` (ver `aws/docs/network/` + `aws/eks/resources/network/`).
- [ ] Decidir base do domínio: delegar `wasp.silvios.me` (ou subzona `aws.wasp.silvios.me`)
      de Azure DNS → Route53, e registrar a hosted zone antes das fatias DNS/ingress/TLS.
- [ ] Definir estratégia de parametrização dos valores hoje em `CLAUDE.local.md`.
- [ ] (nice-to-have) Atribuir permission set SSO (`AdministratorAccess`) à conta `hub` no
      IAM Identity Center — hoje o acesso é via switch role/named profile
      (`OrganizationAccountAccessRole`). Passo a passo em
      `aws/docs/accounts/04-acesso-cross-account.md` (seção TODO).

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.
