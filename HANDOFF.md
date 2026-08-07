# HANDOFF

## Why

Evoluir o Backstage IDP PoC para uma plataforma multi-tenant real, servindo ~120 projetos (clientes) com isolamento estrito de segurança por projeto (uma instância Backstage por projeto, namespaces separados, GitOps repo isolado, GitHub org separada).

Design spec completo em `docs/superpowers/specs/2026-08-07-multi-tenant-idp-design.md`.

Abordagem: Walk Skeleton — exercitar ponta a ponta localmente (k3d) antes de atacar Azure real. O exercício local (k3d + ArgoCD + Crossplane + 10 Azure providers) está concluído em `scripts/cluster-zero/`.

## In Progress

Último passo: plano de implementação do cluster-zero Terraform escrito e commitado em `docs/superpowers/plans/2026-08-07-cluster-zero-terraform.md`. Branch `dev` pushed a `origin`.

**Próximo passo imediato:** executar o plano `2026-08-07-cluster-zero-terraform.md` (Inline Execution ou Subagent-Driven — usuário não escolheu ainda). Escolha foi deixada para a próxima sessão.

## Open Questions / Hypotheses

- Convenção de naming/topics para os repos `azure-*-foundation` existentes ainda não definida — bloqueante para o script de bulk-registration do catálogo (item 5 do backlog).
- Automação de criação dos ~120 repos GitOps por projeto (via `github_repository` Terraform provider ou GitHub API) ainda não planejada — mencionada como risco no spec.
- Subscrição Azure disponível para o apply real do cluster-zero Terraform? (não confirmado — o ciclo de teste do plano é só `fmt`/`validate`/`tflint` por isso).

## Known Broken

1. `idp/app-config.production.yaml` — `guest: {}` presente — **intentional** (PoC; remover antes de produção real).
2. `idp/packages/backend/src/index.ts` — `allow-all` permission policy — **intentional** (PoC; substituir por `PermissionPolicy` real antes de produção).
3. `idp/packages/backend/src/googleAuthModule.ts` — `dangerouslyAllowSignInWithoutUserInCatalog: true` — **intentional** (PoC; restringir por domínio ou catálogo antes de produção).

## How to Resume

```bash
cd /home/silvios/git/backstage
git checkout dev
# Para executar o próximo plano:
cat docs/superpowers/plans/2026-08-07-cluster-zero-terraform.md
```

## Next Steps

### Imediato
- [ ] Executar `docs/superpowers/plans/2026-08-07-cluster-zero-terraform.md` (cluster-zero Terraform: AKS + ArgoCD no Azure real). Escolher Inline Execution (opção 2) ou Subagent-Driven (opção 1).

### Backlog (em ordem de dependência)
- [ ] **#2 Platform Library** — repo central com Crossplane Compositions/XRDs + umbrella Helm chart versionado. Escrever o plano quando o cluster-zero Terraform estiver aplicado (nomes de recursos AKS reais necessários).
- [ ] **#3 GitOps repo por projeto** — ApplicationSet + Kind de onboarding + automação de criação dos repos (~120). Depende de #2.
- [ ] **#4 Provisionamento Backstage por projeto** — Helm chart parametrizado + External Secrets ← AKV. Depende de #2 e #3.
- [ ] **#5 Catálogo Backstage** — Software Template para novos serviços + script de bulk-registration para repos existentes. Depende de convenção de naming acordada com o time.

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.