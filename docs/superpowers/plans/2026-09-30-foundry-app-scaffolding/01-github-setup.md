# GitHub Setup for wasp-foundry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preparar a org `wasp-foundry` para o fluxo: responder o risco de visibilidade do GHCR, criar o repo `gitops` e os dois GitHub Apps com suas credenciais nos lugares certos.

**Architecture:** Quase tudo aqui é configuração no GitHub (via `gh` e, onde não há API, pela UI com o usuário). O único artefato versionado é a atualização do spec com o resultado do spike. Credenciais nunca entram no repo.

**Tech Stack:** `gh` CLI, GitHub Apps, GHCR, GitHub Actions, `backstage-cli create-github-app`.

**Spec:** `docs/superpowers/specs/2026-09-30-foundry-app-scaffolding-design.md` — seções "Credenciais", "`wasp-foundry/gitops`" e "Riscos a validar primeiro". Issue [#101](https://github.com/smsilva/wasp-idp/issues/101).

## Global Constraints

- Org: `wasp-foundry` (plano Free, owner `smsilva`). Tudo público.
- App 1: nome `wasp-foundry-backstage`, instalado em **todos** os repos da org. Permissões de repositório: Administration RW, Contents RW, Pull requests RW, Workflows RW, Metadata R. Nada mais.
- App 2: nome `wasp-foundry-ci`, instalado **só** no repo `gitops`. Permissões: Contents RW, Metadata R. Sem webhook.
- Variável de org `FOUNDRY_CI_APP_ID`, secret de org `FOUNDRY_CI_APP_PRIVATE_KEY`, ambos com visibilidade `all`.
- Arquivo de credenciais do App 1: `idp/github-app-wasp-foundry-backstage-credentials.yaml` (nome exato gerado pela CLI pode variar — ver Task 3). `idp/.gitignore:47` já ignora `*-credentials.yaml`.
- Pré-requisito: plano 00 mergeado e branch `feat/101-foundry-app-scaffolding` rebaseada em `main`.
- Nunca imprimir chave privada; se precisar mostrar, só os 3 primeiros caracteres.

---

### Task 1: Spike — visibilidade inicial de pacote GHCR (throwaway)

Responde o risco 1 do spec. Tudo criado aqui é apagado no fim.

**Files:** nenhum no repo (trabalho em scratchpad).

- [x] **Step 1: Escopos do `gh`**

```bash
gh auth refresh --hostname github.com --scopes read:packages,delete:packages,delete_repo,admin:org
```

(interativo — se o harness não permitir, pedir ao usuário: `! gh auth refresh --hostname github.com --scopes read:packages,delete:packages,delete_repo,admin:org`)

- [x] **Step 2: Repo descartável com workflow de publish**

```bash
spike_dir="$(mktemp --directory)"
cd "${spike_dir}"
git init --initial-branch main
mkdir --parents .github/workflows
printf 'FROM busybox:stable\nCMD ["echo", "spike"]\n' > Dockerfile
cat > .github/workflows/publish.yaml <<'EOF'
name: publish
on: push
jobs:
  publish:
    runs-on: ubuntu-24.04
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        with:
          push: true
          tags: ghcr.io/${{ github.repository }}:latest
          labels: org.opencontainers.image.source=https://github.com/${{ github.repository }}
EOF
git add . && git commit --message "spike"
gh repo create wasp-foundry/ghcr-spike --public --source . --push
```

- [x] **Step 3: Esperar o workflow**

```bash
gh run watch --repo wasp-foundry/ghcr-spike "$(gh run list --repo wasp-foundry/ghcr-spike --limit 1 --json databaseId --jq '.[0].databaseId')"
```

Expected: sucesso.

- [x] **Step 4: Medir visibilidade e pull anônimo**

```bash
gh api orgs/wasp-foundry/packages/container/ghcr-spike --jq '.visibility'
docker logout ghcr.io
docker pull ghcr.io/wasp-foundry/ghcr-spike:latest
```

Resultado A: `public` e pull OK → risco 1 some.
Resultado B: `private` e pull `denied` → antes de decidir, conferir se a org permite pacotes públicos: `https://github.com/organizations/wasp-foundry/settings/packages` → "Package creation" com **Public** marcado. Marcar, apagar o pacote (Step 5), re-rodar o workflow (`gh run rerun`) e medir de novo. Se continuar `private`, **parar e reportar ao usuário** — a decisão entre "tornar público pela UI a cada app" e "pull secret com PAT `read:packages`" é dele.

- [x] **Step 5: Limpeza**

```bash
gh api --method DELETE orgs/wasp-foundry/packages/container/ghcr-spike
gh repo delete wasp-foundry/ghcr-spike --yes
rm --recursive --force "${spike_dir}"
```

- [x] **Step 6: Registrar no spec**

Em `docs/superpowers/specs/2026-09-30-foundry-app-scaffolding-design.md`, seção "Riscos a validar primeiro", item 1: acrescentar ao fim `— **resultado (2026-MM-DD):** <public|private>, <o que foi preciso fazer>`.

```bash
git add docs/superpowers/specs/2026-09-30-foundry-app-scaffolding-design.md
git commit --message "docs(#101): resultado do spike de visibilidade do GHCR"
```

### Task 2: Repo `wasp-foundry/gitops`

**Files:** nenhum no repo `wasp-idp`.

- [x] **Step 1: Criar e popular**

```bash
gitops_dir="$(mktemp --directory)"
cd "${gitops_dir}"
git init --initial-branch main
mkdir apps && touch apps/.gitkeep
cat > README.md <<'EOF'
# gitops

Desired state of every application created by the wasp-idp Backstage template `python-service`.

- `apps/<app>/` — Kustomize base (Deployment, Service). One directory = one ArgoCD `Application`, generated by the `foundry-apps` ApplicationSet.
- New apps arrive by pull request from Backstage. Image tags are bumped by each app's CI with a direct commit to `main`.
EOF
git add . && git commit --message "chore: bootstrap"
gh repo create wasp-foundry/gitops --public --source . --push --description "GitOps desired state for wasp-foundry apps"
rm --recursive --force "${gitops_dir}"
```

- [x] **Step 2: Verificar**

Run: `gh api repos/wasp-foundry/gitops --jq '.visibility, .default_branch'`
Expected: `public` / `main`.

### Task 3: App `wasp-foundry-backstage`

Criação via fluxo de manifest (abre browser) — precisa do usuário.

- [x] **Step 1: Criar**

Pedir ao usuário para rodar:

```
! cd /home/silvios/git/wasp-idp/idp && yarn backstage-cli create-github-app wasp-foundry
```

Na tela do GitHub, o nome do App deve ser `wasp-foundry-backstage`. A CLI grava um `*-credentials.yaml` em `idp/`.

- [x] **Step 2: Conferir o arquivo e que está ignorado**

```bash
ls idp/*-credentials.yaml
git check-ignore --verbose idp/*-credentials.yaml
```

Expected: um arquivo; `check-ignore` aponta `idp/.gitignore:47`. Se o nome não for `github-app-wasp-foundry-backstage-credentials.yaml`, renomear para esse nome (o plano 02 referencia esse caminho).

Conferir que tem as chaves `appId`, `clientId`, `clientSecret`, `webhookSecret`, `privateKey` sem imprimir valores:

```bash
grep --only-matching --extended-regexp '^[a-zA-Z]+:' idp/github-app-wasp-foundry-backstage-credentials.yaml
```

- [x] **Step 3: Permissões** (a CLI cria só com leitura)

Usuário abre `https://github.com/organizations/wasp-foundry/settings/apps/wasp-foundry-backstage/permissions` e define em **Repository permissions**: Administration **Read and write**, Contents **Read and write**, Pull requests **Read and write**, Workflows **Read and write**, Metadata **Read-only**. Todo o resto: No access. Salvar.

- [x] **Step 4: Instalar**

`https://github.com/organizations/wasp-foundry/settings/apps/wasp-foundry-backstage/installations` → Install em `wasp-foundry` → **All repositories**. Se já instalado pela CLI, aceitar as novas permissões em `https://github.com/organizations/wasp-foundry/settings/installations`.

- [x] **Step 5: Verificar**

```bash
gh api orgs/wasp-foundry/installations --jq '.installations[] | select(.app_slug=="wasp-foundry-backstage") | {repository_selection, permissions}'
```

Expected: `repository_selection: "all"` e as cinco permissões com `write`/`read` conforme Step 3.

### Task 4: App `wasp-foundry-ci`

- [x] **Step 1: Criar (usuário, UI)**

`https://github.com/organizations/wasp-foundry/settings/apps/new`:
- GitHub App name: `wasp-foundry-ci`
- Homepage URL: `https://github.com/wasp-foundry/gitops`
- Webhook: desmarcar **Active**
- Repository permissions: Contents **Read and write** (Metadata fica Read-only automaticamente)
- Where can this GitHub App be installed: **Only on this account**

Depois: **Generate a private key** (baixa um `.pem`) e anotar o **App ID**.

- [x] **Step 2: Instalar só no `gitops`**

Install App → `wasp-foundry` → **Only select repositories** → `gitops`.

Verificar:

```bash
gh api orgs/wasp-foundry/installations --jq '.installations[] | select(.app_slug=="wasp-foundry-ci") | {repository_selection, permissions}'
```

Expected: `repository_selection: "selected"`, `contents: "write"`, `metadata: "read"`.

- [x] **Step 3: Variável e secret de org**

```bash
gh variable set FOUNDRY_CI_APP_ID --org wasp-foundry --visibility all --body "<app-id>"
gh secret set FOUNDRY_CI_APP_PRIVATE_KEY --org wasp-foundry --visibility all < "<caminho-do-pem>"
```

- [x] **Step 4: Apagar o `.pem` local**

```bash
shred --remove "<caminho-do-pem>"
```

A chave vive só no secret; para rotacionar, gerar outra na página do App.

- [x] **Step 5: Verificar**

```bash
gh variable list --org wasp-foundry
gh secret list --org wasp-foundry
```

Expected: `FOUNDRY_CI_APP_ID` e `FOUNDRY_CI_APP_PRIVATE_KEY`, visibilidade `ALL`.

Nenhum commit nesta task.
