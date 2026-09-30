# Foundry App Scaffolding Plans

Planos de implementação do spec [`2026-09-30-foundry-app-scaffolding-design.md`](../../specs/2026-09-30-foundry-app-scaffolding-design.md) — issues [#100](https://github.com/smsilva/wasp-idp/issues/100) e [#101](https://github.com/smsilva/wasp-idp/issues/101).

Um arquivo por plano para que cada execução carregue só o contexto que precisa. Cada plano é autocontido: lê o spec + o próprio arquivo, nada mais. Executar **na ordem**; a coluna "Depende de" é bloqueante.

| # | Plano | Issue / branch | Depende de | Entrega verificável |
|---|---|---|---|---|
| 00 | [`00-backstage-upgrade.md`](00-backstage-upgrade.md) | #100 · `feat/100-backstage-upgrade` | — | Backstage 1.55.3, PR mergeado |
| 01 | [`01-github-setup.md`](01-github-setup.md) | #101 · `feat/101-foundry-app-scaffolding` | 00 | Spike GHCR respondido; repo `wasp-foundry/gitops`; dois GitHub Apps; variável e secret de org |
| 02 | [`02-backstage-github.md`](02-backstage-github.md) | #101 | 01 | Backstage publica na `wasp-foundry` via App; `team-alpha`/`team-beta` no catalog |
| 03 | [`03-python-service-template.md`](03-python-service-template.md) | #101 | 02 | Template `python-service` com testes, render check e dry-run verdes |
| 04 | [`04-cluster-zero-foundry.md`](04-cluster-zero-foundry.md) | #101 | 01 | ApplicationSet no k3d; aba Kubernetes do Backstage lê o cluster |
| 05 | [`05-acceptance-and-docs.md`](05-acceptance-and-docs.md) | #101 | 03, 04 | Aceitação ponta a ponta; ADRs; known-broken; PR da #101 |

03 e 04 são independentes entre si (ambos só precisam de 01/02).

## Convenções comuns a todos os planos

- Comandos do Backstage rodam de `idp/`; todo o resto da raiz do repo (`/home/silvios/git/wasp-idp`).
- Scripts bash seguem `~/.claude/rules/bash-scripts.md`: sem extensão, opções longas, 2 espaços, `"${var}"` sempre entre aspas, `do`/`then` na mesma linha.
- Commits em Conventional Commits com escopo da issue (`feat(#101): ...`), terminando com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Ferramentas ausentes nesta máquina rodam via Docker: `shellcheck` → `koalaman/shellcheck:stable`, `actionlint` → `rhysd/actionlint:latest`.
- `gh pr edit` / `gh issue edit` falham neste repo — usar `gh api --method PATCH` (ver `CLAUDE.md`).
- Board #6: project id **`PVT_kwHOAARkfs4Bh2xz`** (o valor em `CLAUDE.md` está errado), field Status `PVTSSF_lAHOAARkfs4Bh2xzzhgw8QM`, `Done` = `1168c952`.
