# Backstage Upgrade 1.49.0 → 1.55.3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Levar o app Backstage de `idp/` da 1.49.0 para a 1.55.3 sem regressão visível, antes de qualquer trabalho da #101.

**Architecture:** `backstage-cli versions:bump` atualiza todas as dependências `@backstage/*`; ajustes manuais só onde os breaking changes 1.50–1.55 tocam este app (chaves `nav-item:*` legadas em `app-config.yaml`). Nenhum código novo.

**Tech Stack:** Backstage 1.55.3, Yarn 4, Node 24.

**Spec:** `docs/superpowers/specs/2026-09-30-foundry-app-scaffolding-design.md` (este plano é a etapa 0 citada no cabeçalho). Issue: [#100](https://github.com/smsilva/wasp-idp/issues/100).

## Global Constraints

- Versão alvo exata: `1.55.3` (não `next`, não `1.56.0-next.*`).
- Node: `22 || 24` (`idp/package.json` `engines`); local é v24.21.0.
- Branch: `feat/100-backstage-upgrade`, criada a partir de `main` atualizada.
- Não mexer em nada da #101 neste branch.

## Fatos já conferidos (não re-derivar)

- `idp/packages/app/src/modules/nav/Sidebar.tsx` já usa `NavContentBlueprint` + `navItems.take('page:...')` — a remoção de `NavItemBlueprint` (1.51) não o afeta. `grep -rn NavItemBlueprint idp/packages` → vazio.
- `idp/app-config.yaml` bloco `app.extensions` tem quatro chaves legadas: `nav-item:search`, `nav-item:user-settings`, `nav-item:catalog`, `nav-item:scaffolder`.
- Sem impacto: claim `ent` (1.50), `FrontendHostDiscovery` (1.52 — não há `discovery.endpoints`), inputs de `github:repo:create` (1.55 — não usado), APIs de catalog removidas (1.55 — nenhum processor customizado).
- 1.53/1.54 endureceram a allowlist de redirect OAuth → testar login Google manualmente.
- `idp/node_modules` não existe nesta máquina — primeiro `yarn install` baixa tudo.

---

### Task 1: Baseline na 1.49.0

**Files:** nenhum.

- [ ] **Step 1: Branch**

```bash
git switch main && git pull --ff-only
git switch --create feat/100-backstage-upgrade
```

- [ ] **Step 2: Instalar e medir o baseline**

```bash
cd idp
yarn install
yarn tsc:full
yarn test:all
```

Expected: tudo verde. Se algo já falha na 1.49.0, anote a saída exata em `/tmp/claude-*/.../scratchpad/baseline.txt` (scratchpad da sessão) — essas falhas não contam como regressão do upgrade. Não corrigir falhas pré-existentes aqui.

### Task 2: Bump para 1.55.3

**Files:**
- Modify: `idp/backstage.json`, `idp/package.json`, `idp/packages/app/package.json`, `idp/packages/backend/package.json`, `idp/yarn.lock` (todos via CLI)

- [ ] **Step 1: Bump**

```bash
cd idp
yarn backstage-cli versions:bump --release 1.55.3
yarn install
```

- [ ] **Step 2: Conferir versão**

Run: `cat backstage.json`
Expected: `{ "version": "1.55.3" }`

- [ ] **Step 3: Warning de módulos da CLI**

Run: `yarn backstage-cli --help 2>&1 | head -5`

Se aparecer aviso de deprecação sobre `@backstage/cli-defaults` ("If no CLI modules are found..."), adicionar como devDependency na raiz:

```bash
yarn add --dev @backstage/cli-defaults
```

e rodar de novo — o aviso deve sumir e `yarn backstage-cli --help` deve listar `create-github-app` (usado no plano 01).

- [ ] **Step 4: Type-check e testes**

```bash
yarn tsc:full
yarn test:all
```

Expected: verde (ou as mesmas falhas do baseline). Se o `tsc` quebrar em `Sidebar.tsx`, `SignInPage.tsx` ou `blueTheme.ts`, consultar `https://raw.githubusercontent.com/backstage/backstage/v1.55.3/docs/releases/v1.5X.0.md` da versão que introduziu a mudança e ajustar o mínimo.

- [ ] **Step 5: Commit**

```bash
git add idp/
git commit --message "chore(#100): bump do Backstage 1.49.0 → 1.55.3"
```

### Task 3: Remover chaves `nav-item:*` legadas

**Files:**
- Modify: `idp/app-config.yaml` (bloco `app.extensions`)

- [ ] **Step 1: Editar**

Remover estas linhas (e o comentário acima delas):

```yaml
    # Disable the nav items that we're manually rendering in packages/app/src/modules/nav/Sidebar.tsx
    - nav-item:search: false
    - nav-item:user-settings: false
    - nav-item:catalog: false
    - nav-item:scaffolder: false
```

- [ ] **Step 2: Smoke manual**

```bash
export GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=...   # pedir ao usuário se não estiverem no ambiente
cd idp && yarn start
```

Em `http://localhost:3000` conferir:
1. Login **guest** entra.
2. Logout → login **Google** entra (valida a allowlist OAuth endurecida em 1.53/1.54).
3. Catalog abre na raiz `/` e lista `example-website`.
4. Sidebar: Search, Catalog, Create, demais páginas, Notifications, Settings — **sem itens duplicados**.
5. `/create` lista "Example Node.js Template".

Se o sidebar mostrar "Settings" duplicado (página `page:user-settings` caindo em `nav.rest`), adicionar em `Sidebar.tsx`, logo abaixo de `nav.take('page:search');`:

```tsx
      nav.take('page:user-settings');
```

e repetir o smoke. Browser automation é opcional; se usada, `claude-in-chrome`.

- [ ] **Step 3: Commit**

```bash
git add idp/app-config.yaml idp/packages/app/src/modules/nav/Sidebar.tsx
git commit --message "fix(#100): remover chaves nav-item legadas do app-config"
```

### Task 4: Documentação

**Files:**
- Modify: `docs/idp/README.md` (linha "**v1.49.0** (`idp/backstage.json`). Toolchain: `@backstage/cli` 0.36.0, ...")
- Modify: `docs/idp/CLAUDE.md` (seção `## Branches`)

- [ ] **Step 1: README** — trocar a versão para `v1.55.3` e a versão do `@backstage/cli` pelo valor de `idp/package.json` após o bump.

- [ ] **Step 2: CLAUDE.md** — a branch `dev` não existe mais; o app vive na `main`. Substituir a seção `## Branches` inteira (tabela + "Always branch from `dev` for feature work on the IDP.") por:

```markdown
## Branches

The Backstage app lives on `main`. Feature work follows the repo convention: `feat/<issue>-<short-description>` from `main`.
```

- [ ] **Step 3: Commit**

```bash
git add docs/idp/
git commit --message "docs(#100): versão 1.55.3 e remoção da branch dev"
```

### Task 5: PR

- [ ] **Step 1: Descrição** em `/tmp/feat-100-backstage-upgrade-pr.txt` (markdown, caminhos relativos ao repo): resumo do bump, breaking changes avaliados (tabela "Fatos já conferidos"), resultado de `tsc:full`/`test:all`, checklist do smoke, `Closes #100`, terminando com `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

- [ ] **Step 2: Push e PR**

```bash
git push --set-upstream origin feat/100-backstage-upgrade
gh pr create --base main --title "chore(#100): upgrade do Backstage para 1.55.3" --body-file /tmp/feat-100-backstage-upgrade-pr.txt
```

Se `gh pr create` falhar, mostrar `https://github.com/smsilva/wasp-idp/compare/feat/100-backstage-upgrade?expand=1`.

- [ ] **Step 3: Após o merge (feito pelo usuário)** — mover #100 para Done:

```bash
gh project item-list 6 --owner smsilva --limit 100 --format json --jq '.items[] | select(.content.number==100) | .id'
gh project item-edit --id <itemId> --project-id PVT_kwHOAARkfs4Bh2xz --field-id PVTSSF_lAHOAARkfs4Bh2xzzhgw8QM --single-select-option-id 1168c952
```

- [ ] **Step 4: Rebase da #101**

```bash
git switch feat/101-foundry-app-scaffolding
git fetch origin && git rebase origin/main
```
