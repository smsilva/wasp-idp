# Acceptance and Docs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provar o fluxo inteiro com uma aplicação real (`hello-alpha`), registrar as decisões (ADRs) e limitações (known-broken) e abrir o PR da #101.

**Architecture:** Nenhum código novo. Execução guiada do template contra a org real e o k3d, seguida de documentação nos lugares que o `CLAUDE.md` da raiz define.

**Tech Stack:** Backstage, GitHub, GHCR, ArgoCD, k3d.

**Spec:** `docs/superpowers/specs/2026-09-30-foundry-app-scaffolding-design.md` — seções "Testes › Aceitação ponta a ponta", "Limitações aceitas" e "ADRs a escrever na implementação". Issue [#101](https://github.com/smsilva/wasp-idp/issues/101).

## Global Constraints

- Aplicação de aceitação: `hello-alpha`, owner `team-alpha`, descrição "Acceptance test app".
- Próximos números de ADR: `0017`, `0018` (último existente: `0016-documentation-navigation-structure.md`). Formato Nygard como os existentes: `# Título em inglês`, `**Status:** Aceito`, `## Contexto`, `## Decisão`, `## Consequências`, corpo em pt-BR.
- `HANDOFF.md` recebe só um resumo de uma linha + data; nada de narrativa.
- Nenhum PII (e-mails) em arquivo versionado.
- Pré-requisito: planos 02, 03 e 04 concluídos.

---

### Task 1: Aceitação ponta a ponta

**Files:** nenhum (se algo falhar, a correção volta para o plano de origem, com commit próprio).

- [ ] **Step 1: Ambiente**

```bash
k3d cluster list | grep idp-cluster-zero || {
  scripts/cluster-zero/cluster-create idp-cluster-zero
  scripts/cluster-zero/install-argocd
}
scripts/cluster-zero/install-foundry-appset
eval "$(scripts/cluster-zero/backstage-reader)"
unset GITHUB_TOKEN
cd idp && yarn start
```

- [ ] **Step 2: Criar pela UI** — login guest → `/create` → "Python service (FastAPI)" → `name: hello-alpha`, descrição "Acceptance test app", owner `team-alpha` → Create. Anotar os três links do output.

- [ ] **Step 3: Checklist** — conferir em ordem, marcando cada item; parar no primeiro que falhar e diagnosticar (skill `superpowers:systematic-debugging`).

1. Repo público:
   ```bash
   gh api repos/wasp-foundry/hello-alpha --jq '.visibility'
   ```
   Expected: `public`. E `.github/workflows/ci.yaml` presente (prova Workflows RW do App).
2. Entidade no catalog: `http://localhost:3000/catalog/default/component/hello-alpha` com Owner `team-alpha`.
3. PR no gitops:
   ```bash
   gh pr list --repo wasp-foundry/gitops --head add-hello-alpha
   gh pr diff --repo wasp-foundry/gitops add-hello-alpha --name-only
   ```
   Expected: um PR; arquivos `apps/hello-alpha/{deployment,service,kustomization}.yaml`. **Merge**:
   ```bash
   gh pr merge --repo wasp-foundry/gitops add-hello-alpha --squash --delete-branch
   ```
4. CI verde e bump:
   ```bash
   gh run watch --repo wasp-foundry/hello-alpha "$(gh run list --repo wasp-foundry/hello-alpha --limit 1 --json databaseId --jq '.[0].databaseId')"
   gh api repos/wasp-foundry/gitops/commits --jq '.[0].commit.message'
   ```
   Expected: jobs `test`, `build`, `bump` verdes. O primeiro push do template tem o mesmo SHA que o PR gravou, então o `bump` do primeiro run termina sem commit — com "is not in gitops yet" (CI rodou antes do merge) ou "Tag already set, nothing to commit" (depois do merge). Ambos corretos. Pacote `ghcr.io/wasp-foundry/hello-alpha` com visibilidade conforme o spike do plano 01.
5. Application:
   ```bash
   kubectl --namespace argocd annotate applicationset foundry-apps argocd.argoproj.io/refresh=normal --overwrite
   kubectl --namespace argocd wait application/hello-alpha --for jsonpath='{.status.health.status}'=Healthy --timeout=300s
   kubectl --namespace argocd get application hello-alpha --output jsonpath='{.status.sync.status} {.status.health.status}'
   ```
   Expected: `Synced Healthy`.
6. HTTP:
   ```bash
   kubectl --namespace hello-alpha port-forward svc/hello-alpha 8080:80 &
   sleep 2
   curl --silent --fail http://localhost:8080/healthz
   curl --silent --fail http://localhost:8080/
   kill %1
   ```
   Expected: `{"status":"ok"}` e `{"app":"hello-alpha","message":"hello"}`.
7. Aba Kubernetes da entidade `hello-alpha`: cluster `cluster-zero`, 1 pod Running.
8. Mudança chega ao cluster:
   ```bash
   work_dir="$(mktemp --directory)"
   gh repo clone wasp-foundry/hello-alpha "${work_dir}"
   sed --in-place 's/"message": "hello"/"message": "hello again"/' "${work_dir}/app/main.py"
   sed --in-place 's/"message": "hello"}/"message": "hello again"}/' "${work_dir}/tests/test_main.py"
   git -C "${work_dir}" commit --all --message "feat: new greeting"
   git -C "${work_dir}" push
   new_sha="$(git -C "${work_dir}" rev-parse HEAD)"
   ```
   Esperar o CI (`gh run watch` como no item 4); então:
   ```bash
   gh api repos/wasp-foundry/gitops/commits --jq '.[0].commit.message'
   kubectl --namespace argocd annotate application hello-alpha argocd.argoproj.io/refresh=normal --overwrite
   kubectl --namespace hello-alpha rollout status deployment/hello-alpha --timeout=300s
   kubectl --namespace hello-alpha get deployment hello-alpha --output jsonpath='{.spec.template.spec.containers[0].image}'
   ```
   Expected: commit `apps(hello-alpha): deploy <7 chars de new_sha>`; imagem `ghcr.io/wasp-foundry/hello-alpha:${new_sha}`; `curl /` (port-forward de novo) → `"hello again"`.

- [ ] **Step 4: Manter `hello-alpha`** como exemplo vivo (não apagar). Remover o clone: `rm --recursive --force "${work_dir}"`.

### Task 2: ADRs

**Files:**
- Create: `docs/adr/0017-central-gitops-repo-for-foundry-apps.md`
- Create: `docs/adr/0018-separate-github-apps-per-role.md`
- Modify: `docs/adr/README.md` (tabela — duas linhas no fim)

- [ ] **Step 1: `0017-central-gitops-repo-for-foundry-apps.md`**

```markdown
# Central GitOps repository for foundry apps

**Status:** Aceito

## Contexto

Aplicações criadas pelo template Backstage `python-service` precisam chegar a um cluster. O Backstage não faz deploy; alguém precisa gravar o estado desejado num Git que o ArgoCD lê. As opções eram manifestos dentro do repo de cada aplicação (pasta `deploy/` + ApplicationSet SCM Provider varrendo a org) ou um repositório central `wasp-foundry/gitops`.

## Decisão

**Repositório central `wasp-foundry/gitops`, um diretório `apps/<app>/` por aplicação.** O template grava a aplicação nova por **pull request** (`publish:github:pull-request`) — o merge é o ponto de revisão da plataforma. O CI de cada aplicação faz **commit direto** do bump de tag (`kustomize edit set image`), porque é mecânico e revisá-lo não agrega. O ArgoCD descobre as aplicações por um `ApplicationSet` com gerador Git directory.

## Consequências

- Duas escritas por criação (repo da app + PR no gitops); o scaffolder não faz rollback, então falha no PR deixa repo órfão (limpeza manual).
- O CI de cada aplicação precisa de credencial de escrita num repo que não é o seu — ver [0018](0018-separate-github-apps-per-role.md).
- Pronto para mais de um ambiente (`apps/<app>/overlays/<env>`) sem mudar o modelo.
- O `smsilva/wasp-gitops` (infra das células) não é usado: aplicação e infraestrutura ficam em repositórios separados.
```

- [ ] **Step 2: `0018-separate-github-apps-per-role.md`**

```markdown
# Separate GitHub Apps per role in wasp-foundry

**Status:** Aceito

## Contexto

Dois atores escrevem na org `wasp-foundry`: o Backstage (cria repos, envia workflows, abre PRs) e o CI de cada aplicação (bump de tag no `gitops`). A chave do CI fica num secret de org, legível por qualquer workflow de qualquer repo da org.

## Decisão

**Dois GitHub Apps.** `wasp-foundry-backstage`: instalado em todos os repos, Administration/Contents/Pull requests/Workflows RW; chave só no arquivo local do Backstage. `wasp-foundry-ci`: instalado **só** no `gitops`, Contents RW; chave no secret de org `FOUNDRY_CI_APP_PRIVATE_KEY`. Tokens de instalação de ~1h, como na [ADR 0012](0012-argocd-github-app-auth.md).

## Consequências

- Um workflow comprometido numa aplicação alcança só o `gitops`, não a criação/remoção de repos da org.
- Continua podendo escrever qualquer caminho do `gitops` — limitação aceita em `aws/docs/known-broken.md`.
- Duas chaves para rotacionar em vez de uma.
```

- [ ] **Step 3: `docs/adr/README.md`** — acrescentar à tabela:

```markdown
| [0017](0017-central-gitops-repo-for-foundry-apps.md) | Repositório GitOps central `wasp-foundry/gitops`: criação por PR, bump de tag por commit direto do CI |
| [0018](0018-separate-github-apps-per-role.md) | Dois GitHub Apps na `wasp-foundry`, um por papel (scaffolding vs. bump de tag) |
```

- [ ] **Step 4: Commit**

```bash
git add docs/adr/
git commit --message "docs(#101): ADRs 0017 e 0018 do fluxo foundry"
```

### Task 3: Known broken, docs do idp e HANDOFF

**Files:**
- Modify: `aws/docs/known-broken.md` (lista numerada em "## Em aberto ou intencional")
- Modify: `docs/idp/README.md` (bloco "Monorepo structure")
- Modify: `HANDOFF.md` (seção "## Completed Work", uma linha)

- [ ] **Step 1: known-broken** — acrescentar ao fim da lista, com o próximo número:

```markdown
N. **Fluxo foundry (#101): CI de qualquer app escreve qualquer caminho do `wasp-foundry/gitops`** — o App `wasp-foundry-ci` tem Contents RW no repo inteiro e sua chave é secret de org; um workflow de uma aplicação pode alterar os manifestos de outra e, via ArgoCD, fazer deploy de qualquer coisa no k3d. Aplicações usam `project: default` (sem isolamento entre times no ArgoCD). Correção futura: `AppProject` por time com `sourceRepos`/`destinations` restritos + ruleset de path no `gitops`. Ver ADR 0018.
```

- [ ] **Step 2: `docs/idp/README.md`** — no bloco de árvore "Monorepo structure", acrescentar as duas pastas novas:

```
├── catalog/        # Catalog data owned by the platform (teams)
├── templates/      # Software Templates (python-service → wasp-foundry)
```

- [ ] **Step 3: `HANDOFF.md`** — no topo da lista da seção "## Completed Work", no formato das entradas existentes (negrito com data e título, depois uma frase):

```markdown
- **2026-MM-DD — #101, criação de aplicação por time na org `wasp-foundry`.** Template Backstage `python-service` cria o repo, CI publica no GHCR e o ApplicationSet `foundry-apps` faz o deploy no k3d do cluster-zero. Spec e planos em `docs/superpowers/{specs,plans}/2026-09-30-foundry-app-scaffolding*`.
```

- [ ] **Step 4: Commit**

```bash
git add aws/docs/known-broken.md docs/idp/README.md HANDOFF.md
git commit --message "docs(#101): known-broken, estrutura do idp e HANDOFF"
```

### Task 4: PR da #101

- [ ] **Step 1: Descrição** em `/tmp/feat-101-foundry-app-scaffolding-pr.txt` (markdown, caminhos relativos ao repo): objetivo, diagrama do spec, lista de arquivos por área (template, cluster-zero, config, docs), resultado do spike GHCR, checklist de aceitação da Task 1 com os resultados, links das ADRs, `Closes #101`, terminando com `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

- [ ] **Step 2: Push e PR**

```bash
git push --set-upstream origin feat/101-foundry-app-scaffolding
gh pr create --base main --title "feat(#101): criar aplicação por time na wasp-foundry com deploy GitOps no k3d" --body-file /tmp/feat-101-foundry-app-scaffolding-pr.txt
```

Se `gh pr create` falhar, mostrar `https://github.com/smsilva/wasp-idp/compare/feat/101-foundry-app-scaffolding?expand=1`.

- [ ] **Step 3: Após o merge (usuário)** — #101 para Done:

```bash
gh project item-list 6 --owner smsilva --limit 100 --format json --jq '.items[] | select(.content.number==101) | .id'
gh project item-edit --id <itemId> --project-id PVT_kwHOAARkfs4Bh2xz --field-id PVTSSF_lAHOAARkfs4Bh2xzzhgw8QM --single-select-option-id 1168c952
```
