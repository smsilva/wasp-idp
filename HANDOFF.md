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

**Próximo passo imediato (direcionamento decidido 2026-08-17):** desenhar a topologia
**hub + spoke conectada**, e a partir daí **avaliar se o TGW é necessário** para essa
conexão ou se há caminho mais simples (VPC peering? conta única com 1 VPC? spoke na mesma
conta hub?). NÃO aplicar a `Network` como está antes desse desenho — a premissa da PoC é
Well-Architected hub-and-spoke, e a `Network` atual é uma **VPC isolada, não um spoke**
(faltam TGW attachment, CIDR parametrizado e rota `<remote-cidr> → TGW`).

Contexto para a retomada (confirmado nesta sessão):
- **Direcionamento hub-and-spoke ESTÁ claro nas docs** (`aws/docs/network/00`, `02`, `03`):
  TGW central, isolamento por `tgw-rt-<spoke>`, RAM cross-account, conta-por-projeto.
- **O que falta decidir** é o *degrau de bootstrap*: começar com hub+1 spoke na PoC pessoal
  precisa mesmo de TGW? A doc `03` admite "cenário de conta única" onde RAM/attachment são
  suprimidos. Pesar TGW (alvo, isolamento real, custo/complexidade) vs. peering/conta-única
  (mais simples, sem isolamento por route-table) para o primeiro par hub↔spoke.
- **Gap 1 (CIDR fixo `172.16.0.0/16`)** continua sendo pré-requisito irreversível: qualquer
  spoke real precisa de CIDR parametrizado + alinhado à supernet (`aws/docs/network/01`, `07`).
  Definir a supernet concreta (hoje placeholder `<supernet>`) faz parte do desenho.
- Hub Crossplane (k3d) já está 100% pronto para aplicar XRs quando o desenho fechar.

Opções levantadas (não escolhidas): A=aplicar VPC isolada como está (re-endereça depois);
B=parametrizar CIDR primeiro, aplicar VPC endereçável-como-spoke sem TGW; C=ir ao alvo
completo (XR HubNetwork+TGW+RAM, marcado "futuro" no mapa). Retomar pela pergunta do TGW.

## Open Questions / Hypotheses

- **TGW necessário para o 1º par hub↔spoke? (pergunta de retomada):** avaliar se conectar
  uma spoke à hub na PoC pessoal exige Transit Gateway (alvo WAF, isolamento por route-table,
  custo/complexidade) ou se um caminho mais simples (VPC peering, ou hub+spoke na mesma conta)
  basta para o degrau de bootstrap. A doc `network/03` admite "cenário de conta única" com
  RAM/attachment suprimidos. Decidir antes de aplicar qualquer `Network`.
- **Supernet concreta (a decidir):** o plano de endereçamento (`network/01`) usa placeholder
  `<supernet>`; escolher o bloco real (/12–/14) e a alocação por spoke é pré-requisito de
  parametrizar o CIDR (Gap 1) — irreversível depois do 1º apply.
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
