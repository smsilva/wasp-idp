# Bookinfo Catalog and Multi-Cluster Plans

Planos de implementação do spec [`2026-10-01-bookinfo-catalog-multi-cluster-design.md`](../../specs/2026-10-01-bookinfo-catalog-multi-cluster-design.md) — issue [#105](https://github.com/smsilva/wasp-idp/issues/105), branch `feat/105-bookinfo-catalog-multi-cluster`.

Um arquivo por plano para que cada execução carregue só o contexto que precisa. Cada plano é autocontido: lê o spec + o próprio arquivo. Executar **na ordem**; a coluna "Depende de" é bloqueante.

| # | Plano | Depende de | Entrega verificável |
|---|---|---|---|
| 00 | [`00-spike-cross-cluster.md`](00-spike-cross-cluster.md) | — | Risco 1 respondido: endereço e TLS com que o ArgoCD alcança outro k3d pela rede `k3d-idp` |
| 01 | [`01-clusters-and-argocd.md`](01-clusters-and-argocd.md) | 00 | `idp-cluster-zero`, `development`, `production` na rede `k3d-idp`; os dois registrados no ArgoCD; Backstage lê os dois |
| 02 | [`02-gitops-environments.md`](02-gitops-environments.md) | 01 | `gitops` em base + overlays; ApplicationSet matrix; `promote.yaml`; `hello-alpha` e template migrados |
| 03 | [`03-catalog-discovery.md`](03-catalog-discovery.md) | — | Domain/System/Resources no catalog; descoberta automática da org `wasp-foundry` |
| 04 | [`04-bookinfo-seed.md`](04-bookinfo-seed.md) | 02, 03 | Quatro repos Bookinfo, CI verde, apps `Synced Healthy` nos dois clusters, `productpage` em `:9081`/`:9082` |
| 05 | [`05-acceptance-and-docs.md`](05-acceptance-and-docs.md) | 04 | Aceitação ponta a ponta; ADRs 0019/0020; known-broken; PR da #105 |

03 não depende de 00–02 e pode rodar a qualquer momento antes do 04.

## Convenções comuns a todos os planos

- Comandos do Backstage rodam de `idp/` com `node .yarn/releases/yarn-4.4.1.cjs <cmd>` (`yarn` não está no `PATH`); todo o resto da raiz do repo (`/home/silvios/git/wasp-idp`).
- Scripts bash seguem `~/.claude/rules/bash-scripts.md`: sem extensão, opções longas, 2 espaços, `"${var}"` sempre entre aspas, `do`/`then` na mesma linha, mensagens em inglês.
- Commits em Conventional Commits com escopo da issue (`feat(#105): ...`), terminando com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Ferramentas ausentes rodam via Docker: `shellcheck` → `koalaman/shellcheck:stable`, `actionlint` → `rhysd/actionlint:latest` (passar o caminho do arquivo — o diretório não é repo git), `redocly` → `redocly/cli:latest`.
- `gh repo clone` falha nesta máquina com "error connecting to api.github.com" — usar `git clone git@github.com:<org>/<repo>.git`.
- Com vários clusters, **todo `kubectl`/`helm` que não seja do cluster-zero leva `--context k3d-<nome>`**; `k3d cluster create` troca o contexto corrente para o cluster recém-criado.
- `gh pr edit` / `gh issue edit` falham neste repo — usar `gh api --method PATCH` (ver `CLAUDE.md`).
- Backstage local: banco `:memory:`, locations novas do `app-config.yaml` só valem após reiniciar o `yarn start`. Parar o backend pelos PIDs que escutam `:3000`/`:7007` (`ss -ltnp`), nunca `pkill -f` com padrão do comando.
