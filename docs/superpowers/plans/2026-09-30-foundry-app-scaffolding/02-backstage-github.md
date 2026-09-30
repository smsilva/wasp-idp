# Backstage GitHub App and Teams Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O Backstage passa a autenticar no GitHub pelo App `wasp-foundry-backstage` (no lugar do PAT) e o catalog passa a ter os times `team-alpha` e `team-beta`.

**Architecture:** Só configuração: `integrations.github[0].apps` com `$include` do arquivo de credenciais gerado no plano 01, e um `org.yaml` novo registrado como location do catalog. Backend e frontend não mudam.

**Tech Stack:** Backstage 1.55.3 (`app-config.yaml`, catalog `Group`).

**Spec:** `docs/superpowers/specs/2026-09-30-foundry-app-scaffolding-design.md` — seção "Componentes › `idp/` (Backstage)". Issue [#101](https://github.com/smsilva/wasp-idp/issues/101).

## Global Constraints

- Arquivo de credenciais: `idp/github-app-wasp-foundry-backstage-credentials.yaml` (criado no plano 01, Task 3; ignorado por `idp/.gitignore:47`).
- Times: `team-alpha`, `team-beta`, `spec.type: team`.
- Locations do catalog são relativas a `idp/packages/backend/` (processo do backend) — por isso `../../`.
- Não alterar `idp/app-config.production.yaml` (fora de escopo: o fluxo roda só em dev local).
- Branch: `feat/101-foundry-app-scaffolding`.

---

### Task 1: Times no catalog

**Files:**
- Create: `idp/catalog/org.yaml`
- Modify: `idp/app-config.yaml` (bloco `catalog.locations`)

- [ ] **Step 1: Criar `idp/catalog/org.yaml`**

```yaml
---
# https://backstage.io/docs/features/software-catalog/descriptor-format#kind-group
apiVersion: backstage.io/v1alpha1
kind: Group
metadata:
  name: team-alpha
  description: Example product team (owner of apps created from the python-service template)
spec:
  type: team
  children: []
---
apiVersion: backstage.io/v1alpha1
kind: Group
metadata:
  name: team-beta
  description: Example product team (owner of apps created from the python-service template)
spec:
  type: team
  children: []
```

- [ ] **Step 2: Registrar a location** — em `idp/app-config.yaml`, logo após a location de `../../examples/org.yaml`, acrescentar:

```yaml
    # Product teams (owners in the python-service template)
    - type: file
      target: ../../catalog/org.yaml
      rules:
        - allow: [Group]
```

- [ ] **Step 3: Verificar**

```bash
cd idp && yarn start
```

Em `http://localhost:3000/catalog?filters[kind]=group` (login guest): `team-alpha`, `team-beta` e `guests` listados.

- [ ] **Step 4: Commit**

```bash
git add idp/catalog/org.yaml idp/app-config.yaml
git commit --message "feat(#101): grupos team-alpha e team-beta no catalog"
```

### Task 2: GitHub App no lugar do PAT

**Files:**
- Modify: `idp/app-config.yaml` (bloco `integrations.github`)

- [ ] **Step 1: Editar** — substituir o item `github.com` inteiro (inclusive o comentário do PAT e a linha `token: ${GITHUB_TOKEN}`) por:

```yaml
integrations:
  github:
    - host: github.com
      # GitHub App wasp-foundry-backstage, created with `yarn backstage-cli create-github-app wasp-foundry`.
      # The credentials file is gitignored (idp/.gitignore: *-credentials.yaml).
      apps:
        - $include: github-app-wasp-foundry-backstage-credentials.yaml
```

Manter o bloco comentado de exemplo do GitHub Enterprise que vem abaixo.

- [ ] **Step 2: Validar a config**

```bash
cd idp && yarn backstage-cli config:check --lax
```

Expected: sem erro. (`--lax` porque `GOOGLE_CLIENT_*` podem não estar no ambiente.)

- [ ] **Step 3: Smoke — App cria repo na org**

Sem `GITHUB_TOKEN` no ambiente (`unset GITHUB_TOKEN`), `yarn start`, login guest, `/create` → "Example Node.js Template":
- Name: `app-smoke`
- Repository Location: owner `wasp-foundry`, repo `app-smoke`

Expected: task conclui; `gh api repos/wasp-foundry/app-smoke --jq .full_name` → `wasp-foundry/app-smoke`. Isso prova Administration + Contents do App. (Workflows RW é exercitado no plano 05, porque o template de exemplo não tem `.github/workflows`.)

Se falhar com `Resource not accessible by integration`, a permissão correspondente não foi aceita na instalação — voltar ao plano 01, Task 3, Steps 3–5.

- [ ] **Step 4: Limpeza do smoke**

```bash
gh repo delete wasp-foundry/app-smoke --yes
```

Remover a entidade `app-smoke` do catalog: na página da entidade → menu ⋮ → "Unregister entity".

- [ ] **Step 5: Commit**

```bash
git add idp/app-config.yaml
git commit --message "feat(#101): integração GitHub via App wasp-foundry-backstage"
```

- [ ] **Step 6: Atualizar a doc de execução local** — em `docs/idp/CLAUDE.md`, acrescentar ao fim da seção `## Authentication` (antes de `## Scripts`):

```markdown
### GitHub integration

The backend authenticates to GitHub as the App `wasp-foundry-backstage` (org `wasp-foundry`), not a PAT. `idp/app-config.yaml` includes `idp/github-app-wasp-foundry-backstage-credentials.yaml`, which is gitignored and must exist locally before `yarn start`. To recreate it: `yarn backstage-cli create-github-app wasp-foundry`, then raise the permissions to Administration/Contents/Pull requests/Workflows RW in the App settings (the CLI creates it read-only).
```

```bash
git add docs/idp/CLAUDE.md
git commit --message "docs(#101): integração GitHub via App no CLAUDE.md do idp"
```
