# Python Service Template Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Software Template `python-service` que cria o repo da aplicação FastAPI na `wasp-foundry`, abre PR com os manifestos em `wasp-foundry/gitops` e registra a entidade no catalog.

**Architecture:** Três pastas sob `idp/templates/python-service/`: `content/` (vira o repo da aplicação), `gitops/` (vira `apps/<name>/` no `gitops`) e `template.yaml`. O código Python não é templatado (lê `APP_NAME` do ambiente), então é testável direto com pytest. O workflow de CI é copiado sem templating. Um script `test-render` renderiza os arquivos templatados com valores fixos e valida o Kustomize.

**Tech Stack:** Backstage scaffolder (`fetch:template`, `publish:github`, `publish:github:pull-request`, `catalog:register`), Python 3.13, FastAPI, uvicorn, pytest, httpx, Docker, Kustomize, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-30-foundry-app-scaffolding-design.md` — seções "Template", "CI da aplicação" e "Tratamento de erros". Issue [#101](https://github.com/smsilva/wasp-idp/issues/101).

## Global Constraints

- Owner fixo dos repos: `wasp-foundry`. Repo GitOps: `wasp-foundry/gitops`, caminho `apps/<name>/`.
- `name`: regex `^[a-z]([-a-z0-9]{0,38}[a-z0-9])?$`.
- Imagem: `ghcr.io/wasp-foundry/<name>:<sha completo>`. Nome da imagem no Kustomize: `app`.
- Porta do container: `8000`; Service `80 → 8000`; probes em `/healthz`.
- Label obrigatória no Deployment **e** no Pod template: `backstage.io/kubernetes-id: <name>`.
- Imagem base: `python:3.13-slim`; container roda como UID `10001`.
- Variáveis do CI: `vars.FOUNDRY_CI_APP_ID`, `secrets.FOUNDRY_CI_APP_PRIVATE_KEY` (criadas no plano 01).
- `.github/workflows/*` fica em `copyWithoutTemplating` — nunca usar `${{ values.* }}` no workflow.
- Pré-requisito: plano 02 concluído (App e times funcionando).

## File Structure

```
idp/templates/python-service/
├── template.yaml                 # scaffolder template (parâmetros, passos, output)
├── test-render                   # bash: renderiza gitops/ + catalog-info com valores fixos e valida
├── content/                      # → repo wasp-foundry/<name>
│   ├── .github/workflows/ci.yaml # test → build → bump (não templatado)
│   ├── .dockerignore
│   ├── Dockerfile
│   ├── README.md                 # templatado
│   ├── catalog-info.yaml         # templatado
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── app/__init__.py
│   ├── app/main.py
│   └── tests/test_main.py
└── gitops/                       # → wasp-foundry/gitops: apps/<name>/
    ├── deployment.yaml           # templatado
    ├── service.yaml              # templatado
    └── kustomization.yaml        # templatado
```

---

### Task 1: Aplicação FastAPI (TDD)

**Files:**
- Create: `idp/templates/python-service/content/app/__init__.py` (vazio)
- Create: `idp/templates/python-service/content/app/main.py`
- Create: `idp/templates/python-service/content/tests/test_main.py`
- Create: `idp/templates/python-service/content/requirements.txt`
- Create: `idp/templates/python-service/content/requirements-dev.txt`

**Interfaces:**
- Produces: módulo `app.main` com objeto ASGI `app` (usado pelo `Dockerfile`: `uvicorn app.main:app`); env var `APP_NAME` (definida pelo `deployment.yaml` da Task 3).

- [x] **Step 1: Resolver versões atuais**

```bash
for package in fastapi uvicorn pytest httpx; do
  pip index versions "${package}" 2>/dev/null | head -1
done
```

Usar as versões mais recentes exibidas nos arquivos abaixo (substituindo `X.Y.Z`).

- [x] **Step 2: Dependências**

`requirements.txt`:

```
fastapi==X.Y.Z
uvicorn==X.Y.Z
```

`requirements-dev.txt`:

```
pytest==X.Y.Z
httpx==X.Y.Z
```

- [x] **Step 3: Teste que falha** — `tests/test_main.py`:

```python
import importlib

from fastapi.testclient import TestClient

import app.main


def client_with_name(monkeypatch, name):
    if name is None:
        monkeypatch.delenv("APP_NAME", raising=False)
    else:
        monkeypatch.setenv("APP_NAME", name)
    return TestClient(importlib.reload(app.main).app)


def test_healthz_returns_ok(monkeypatch):
    client = client_with_name(monkeypatch, None)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_returns_app_name_from_environment(monkeypatch):
    client = client_with_name(monkeypatch, "hello-alpha")
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"app": "hello-alpha", "message": "hello"}


def test_root_falls_back_to_default_name(monkeypatch):
    client = client_with_name(monkeypatch, None)
    assert client.get("/").json()["app"] == "python-service"
```

- [x] **Step 4: Rodar e ver falhar**

```bash
cd idp/templates/python-service/content
python3 -m venv .venv && . .venv/bin/activate
pip install --requirement requirements.txt --requirement requirements-dev.txt
touch app/__init__.py
pytest
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.main'`.

- [x] **Step 5: Implementação** — `app/main.py`:

```python
import os

from fastapi import FastAPI

APP_NAME = os.environ.get("APP_NAME", "python-service")

app = FastAPI(title=APP_NAME)


@app.get("/")
def root() -> dict[str, str]:
    return {"app": APP_NAME, "message": "hello"}


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
```

- [x] **Step 6: Rodar e ver passar**

Run: `pytest`
Expected: `3 passed`.

- [x] **Step 7: Não versionar o venv** — confirmar `git status --short idp/templates/` sem `.venv/`; se aparecer, criar `idp/templates/python-service/content/.gitignore` com:

```
.venv/
__pycache__/
.pytest_cache/
```

(esse `.gitignore` também vai para o repo gerado, o que é desejável.)

- [x] **Step 8: Commit**

```bash
git add idp/templates/python-service/content
git commit --message "feat(#101): aplicação FastAPI do template python-service"
```

### Task 2: Dockerfile

**Files:**
- Create: `idp/templates/python-service/content/Dockerfile`
- Create: `idp/templates/python-service/content/.dockerignore`

- [x] **Step 1: `Dockerfile`**

```dockerfile
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir --requirement requirements.txt

COPY app/ app/

USER 10001

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [x] **Step 2: `.dockerignore`**

```
.git
.github
.venv
__pycache__
.pytest_cache
tests
```

- [x] **Step 3: Build e run**

```bash
cd idp/templates/python-service/content
docker build --tag python-service:test .
docker run --detach --rm --name python-service-test --publish 18000:8000 --env APP_NAME=docker-test python-service:test
sleep 3
curl --silent --fail http://localhost:18000/healthz
curl --silent --fail http://localhost:18000/
docker stop python-service-test
```

Expected: `{"status":"ok"}` e `{"app":"docker-test","message":"hello"}`.

- [x] **Step 4: Commit**

```bash
git add idp/templates/python-service/content/Dockerfile idp/templates/python-service/content/.dockerignore
git commit --message "feat(#101): Dockerfile do template python-service"
```

### Task 3: Arquivos templatados + `test-render`

**Files:**
- Create: `idp/templates/python-service/gitops/deployment.yaml`
- Create: `idp/templates/python-service/gitops/service.yaml`
- Create: `idp/templates/python-service/gitops/kustomization.yaml`
- Create: `idp/templates/python-service/content/catalog-info.yaml`
- Create: `idp/templates/python-service/content/README.md`
- Create: `idp/templates/python-service/test-render`

**Interfaces:**
- Consumes: `APP_NAME` e porta `8000` (Task 1/2).
- Produces: valores de template `values.name`, `values.description`, `values.owner` (content) e `values.name`, `values.imageTag` (gitops) — preenchidos pelo `template.yaml` da Task 5.

- [x] **Step 1: Teste que falha — `test-render`**

```bash
#!/bin/bash
# Render the python-service template files with fixed values and validate them.
# Fails if Kustomize cannot build apps/<name>/ or if required fields are missing.
set -e

this_script_path="$(realpath "${0}")"
this_script_directory="${this_script_path%/*}"

name="render-test"
image_tag="0123456789abcdef0123456789abcdef01234567"
owner="group:default/team-alpha"
description="Render test"

render_directory="$(mktemp --directory)"
trap 'rm --recursive --force "${render_directory}"' EXIT

render() {
  local source_file="${1?}"
  local target_file="${2?}"

  sed \
    --expression "s|\${{ values.name }}|${name}|g" \
    --expression "s|\${{ values.imageTag }}|${image_tag}|g" \
    --expression "s|\${{ values.owner }}|${owner}|g" \
    --expression "s|\${{ values.description }}|${description}|g" \
    "${source_file}" > "${target_file}"

  if grep --quiet '\${{' "${target_file}"; then
    echo "Unrendered expression left in ${target_file}:" >&2
    grep --line-number '\${{' "${target_file}" >&2
    exit 1
  fi
}

mkdir --parents "${render_directory}/gitops"

for file in "${this_script_directory}"/gitops/*.yaml; do
  render "${file}" "${render_directory}/gitops/${file##*/}"
done

render \
  "${this_script_directory}/content/catalog-info.yaml" \
  "${render_directory}/catalog-info.yaml"

manifests="$(kubectl kustomize "${render_directory}/gitops")"

check() {
  local description="${1?}"
  local pattern="${2?}"

  if ! grep --quiet --fixed-strings -- "${pattern}" <<< "${manifests}"; then
    echo "FAIL: ${description} (missing: ${pattern})" >&2
    exit 1
  fi
  echo "ok: ${description}"
}

check "image rewritten by kustomize" "image: ghcr.io/wasp-foundry/${name}:${image_tag}"
check "backstage kubernetes-id label" "backstage.io/kubernetes-id: ${name}"
check "APP_NAME env" "value: ${name}"
check "service targets named port" "targetPort: http"

if [[ "$(grep --count "backstage.io/kubernetes-id: ${name}" <<< "${manifests}")" -lt 3 ]]; then
  echo "FAIL: kubernetes-id label must be on Deployment, Pod template and Service" >&2
  exit 1
fi
echo "ok: kubernetes-id label on Deployment, Pod template and Service"

if kubectl version --request-timeout=3s > /dev/null 2>&1; then
  kubectl apply --dry-run=server --filename - <<< "${manifests}" > /dev/null
  echo "ok: server-side dry-run"
else
  echo "skip: server-side dry-run (no reachable cluster)"
fi

grep --quiet "owner: ${owner}" "${render_directory}/catalog-info.yaml"
grep --quiet "backstage.io/kubernetes-id: ${name}" "${render_directory}/catalog-info.yaml"
grep --quiet "github.com/project-slug: wasp-foundry/${name}" "${render_directory}/catalog-info.yaml"
echo "ok: catalog-info.yaml"
```

```bash
chmod +x idp/templates/python-service/test-render
```

- [x] **Step 2: Rodar e ver falhar**

Run: `idp/templates/python-service/test-render`
Expected: FAIL — `sed: can't read .../gitops/*.yaml` (arquivos ainda não existem).

- [x] **Step 3: `gitops/deployment.yaml`**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ${{ values.name }}
  labels:
    app.kubernetes.io/name: ${{ values.name }}
    backstage.io/kubernetes-id: ${{ values.name }}
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: ${{ values.name }}
  template:
    metadata:
      labels:
        app.kubernetes.io/name: ${{ values.name }}
        backstage.io/kubernetes-id: ${{ values.name }}
    spec:
      securityContext:
        runAsNonRoot: true
      containers:
        - name: app
          image: app
          ports:
            - name: http
              containerPort: 8000
          env:
            - name: APP_NAME
              value: ${{ values.name }}
          readinessProbe:
            httpGet:
              path: /healthz
              port: http
          livenessProbe:
            httpGet:
              path: /healthz
              port: http
          resources:
            requests:
              cpu: 50m
              memory: 64Mi
            limits:
              memory: 128Mi
```

- [x] **Step 4: `gitops/service.yaml`**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: ${{ values.name }}
  labels:
    app.kubernetes.io/name: ${{ values.name }}
    backstage.io/kubernetes-id: ${{ values.name }}
spec:
  type: ClusterIP
  selector:
    app.kubernetes.io/name: ${{ values.name }}
  ports:
    - name: http
      port: 80
      targetPort: http
```

- [x] **Step 5: `gitops/kustomization.yaml`**

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - deployment.yaml
  - service.yaml
images:
  - name: app
    newName: ghcr.io/wasp-foundry/${{ values.name }}
    newTag: ${{ values.imageTag }}
```

- [x] **Step 6: `content/catalog-info.yaml`**

```yaml
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: ${{ values.name }}
  description: ${{ values.description }}
  annotations:
    github.com/project-slug: wasp-foundry/${{ values.name }}
    backstage.io/kubernetes-id: ${{ values.name }}
spec:
  type: service
  lifecycle: experimental
  owner: ${{ values.owner }}
```

- [x] **Step 7: `content/README.md`**

```markdown
# ${{ values.name }}

${{ values.description }}

FastAPI service created from the wasp-idp Backstage template `python-service`.

- `GET /` — app name and a greeting
- `GET /healthz` — liveness/readiness

Every push to `main` runs the tests, publishes `ghcr.io/wasp-foundry/${{ values.name }}:<sha>` and bumps the tag in [`wasp-foundry/gitops`](https://github.com/wasp-foundry/gitops/tree/main/apps/${{ values.name }}), which ArgoCD deploys.

## Local run

    python3 -m venv .venv && . .venv/bin/activate
    pip install --requirement requirements.txt --requirement requirements-dev.txt
    pytest
    uvicorn app.main:app --reload
```

- [x] **Step 8: Rodar e ver passar**

Run: `idp/templates/python-service/test-render`
Expected: todas as linhas `ok:`; `skip: server-side dry-run` se não houver k3d no ar (aceitável — o plano 05 roda com cluster).

- [x] **Step 9: shellcheck**

```bash
docker run --rm --volume "${PWD}:/mnt" --workdir /mnt koalaman/shellcheck:stable idp/templates/python-service/test-render
```

Expected: sem saída.

- [x] **Step 10: Commit**

```bash
git add idp/templates/python-service/gitops idp/templates/python-service/content/catalog-info.yaml idp/templates/python-service/content/README.md idp/templates/python-service/test-render
git commit --message "feat(#101): manifestos gitops e catalog-info do template python-service"
```

### Task 4: Workflow de CI da aplicação

**Files:**
- Create: `idp/templates/python-service/content/.github/workflows/ci.yaml`

- [x] **Step 1: Resolver majors atuais das actions**

```bash
for action in actions/checkout actions/setup-python docker/login-action docker/build-push-action actions/create-github-app-token; do
  echo "${action} $(gh api "repos/${action}/releases/latest" --jq .tag_name)"
done
```

Usar o major de cada uma (`vN`) no arquivo abaixo, substituindo os `@vN` se forem diferentes.

- [x] **Step 2: `ci.yaml`**

```yaml
name: ci

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.13'
      - run: pip install --requirement requirements.txt --requirement requirements-dev.txt
      - run: pytest

  build:
    needs: test
    if: github.event_name == 'push'
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
          tags: ghcr.io/${{ github.repository }}:${{ github.sha }}
          labels: org.opencontainers.image.source=https://github.com/${{ github.repository }}

  bump:
    needs: build
    runs-on: ubuntu-24.04
    steps:
      - id: app-token
        uses: actions/create-github-app-token@v1
        with:
          app-id: ${{ vars.FOUNDRY_CI_APP_ID }}
          private-key: ${{ secrets.FOUNDRY_CI_APP_PRIVATE_KEY }}
          owner: ${{ github.repository_owner }}
          repositories: gitops
      - uses: actions/checkout@v4
        with:
          repository: ${{ github.repository_owner }}/gitops
          token: ${{ steps.app-token.outputs.token }}
          path: gitops
      - name: Set image tag
        id: set-image
        env:
          APP: ${{ github.event.repository.name }}
          IMAGE: ghcr.io/${{ github.repository }}:${{ github.sha }}
        run: |
          if [[ ! -d "gitops/apps/${APP}" ]]; then
            echo "apps/${APP} is not in gitops yet (creation PR not merged); the PR already pins this commit's tag"
            echo "skip=true" >> "${GITHUB_OUTPUT}"
            exit 0
          fi
          cd "gitops/apps/${APP}"
          kustomize edit set image "app=${IMAGE}"
      - name: Commit and push
        if: steps.set-image.outputs.skip != 'true'
        working-directory: gitops
        env:
          APP: ${{ github.event.repository.name }}
          SHA: ${{ github.sha }}
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add "apps/${APP}/kustomization.yaml"
          if git diff --cached --quiet; then
            echo "Tag already set, nothing to commit"
            exit 0
          fi
          git commit --message "apps(${APP}): deploy ${SHA::7}"
          for attempt in 1 2 3; do
            if git push; then
              exit 0
            fi
            echo "Push rejected (attempt ${attempt}), rebasing"
            git pull --rebase
          done
          echo "Could not push after 3 attempts" >&2
          exit 1
```

Nota: `kustomize` vem pré-instalado na imagem `ubuntu-24.04` dos runners. Se o job falhar com `kustomize: command not found`, adicionar antes de "Set image tag" o passo `- uses: imranismail/setup-kustomize@v2`.

- [x] **Step 3: actionlint**

```bash
docker run --rm --volume "${PWD}/idp/templates/python-service/content:/repo" --workdir /repo rhysd/actionlint:latest -color
```

Expected: sem erros.

- [x] **Step 4: Commit**

```bash
git add idp/templates/python-service/content/.github
git commit --message "feat(#101): CI do template python-service (test, build, bump no gitops)"
```

### Task 5: `template.yaml` e registro no catalog

**Files:**
- Create: `idp/templates/python-service/template.yaml`
- Modify: `idp/app-config.yaml` (bloco `catalog.locations`)

**Interfaces:**
- Consumes: `content/` (values `name`, `description`, `owner`), `gitops/` (values `name`, `imageTag`), `Group`s do plano 02.

- [x] **Step 1: `template.yaml`**

```yaml
apiVersion: scaffolder.backstage.io/v1beta3
kind: Template
metadata:
  name: python-service
  title: Python service (FastAPI)
  description: Creates a FastAPI service in the wasp-foundry GitHub org, with CI to GHCR and deployment to the cluster-zero k3d via GitOps.
  tags:
    - python
    - fastapi
spec:
  owner: group:default/guests
  type: service

  parameters:
    - title: Service
      required:
        - name
        - description
        - owner
      properties:
        name:
          title: Name
          type: string
          description: Repository, namespace and image name. Lowercase letters, digits and hyphens.
          pattern: '^[a-z]([-a-z0-9]{0,38}[a-z0-9])?$'
          ui:autofocus: true
        description:
          title: Description
          type: string
        owner:
          title: Owner team
          type: string
          ui:field: OwnerPicker
          ui:options:
            catalogFilter:
              kind: Group

  steps:
    - id: fetch-app
      name: Render application
      action: fetch:template
      input:
        url: ./content
        copyWithoutTemplating:
          - .github/workflows/*
        values:
          name: ${{ parameters.name }}
          description: ${{ parameters.description }}
          owner: ${{ parameters.owner }}

    - id: publish
      name: Create repository
      action: publish:github
      input:
        repoUrl: github.com?owner=wasp-foundry&repo=${{ parameters.name }}
        description: ${{ parameters.description }}
        repoVisibility: public
        defaultBranch: main

    - id: fetch-gitops
      name: Render GitOps manifests
      action: fetch:template
      input:
        url: ./gitops
        targetPath: ./gitops-pr
        values:
          name: ${{ parameters.name }}
          imageTag: ${{ steps['publish'].output.commitHash }}

    - id: gitops-pr
      name: Open GitOps pull request
      action: publish:github:pull-request
      input:
        repoUrl: github.com?owner=wasp-foundry&repo=gitops
        sourcePath: ./gitops-pr
        targetPath: apps/${{ parameters.name }}
        branchName: add-${{ parameters.name }}
        title: 'apps: add ${{ parameters.name }}'
        description: |
          Deploys `${{ parameters.name }}` (owner `${{ parameters.owner }}`) to cluster-zero.
          Created by the Backstage template `python-service`.

    - id: register
      name: Register in catalog
      action: catalog:register
      input:
        repoContentsUrl: ${{ steps['publish'].output.repoContentsUrl }}
        catalogInfoPath: /catalog-info.yaml

  output:
    links:
      - title: Repository
        url: ${{ steps['publish'].output.remoteUrl }}
      - title: GitOps pull request
        url: ${{ steps['gitops-pr'].output.remoteUrl }}
      - title: Open in catalog
        icon: catalog
        entityRef: ${{ steps['register'].output.entityRef }}
```

- [x] **Step 2: Location** — em `idp/app-config.yaml`, logo após a location do template de exemplo (`../../examples/template/template.yaml`):

```yaml
    # Foundry templates (apps created in the wasp-foundry GitHub org)
    - type: file
      target: ../../templates/python-service/template.yaml
      rules:
        - allow: [Template]
```

- [x] **Step 3: Dry-run no Template Editor**

`cd idp && yarn start`, login guest, `http://localhost:3000/create/edit` → "Load Template Directory" → selecionar `idp/templates/python-service/` → preencher `name: dry-run-test`, uma descrição, owner `team-alpha` → **Create** (modo dry-run).

Expected:
- Passos `fetch-app` e `fetch-gitops` executam; `publish`, `gitops-pr` e `register` aparecem como dry-run (não publicam nada).
- No painel de arquivos: `catalog-info.yaml` com `owner: group:default/team-alpha`; `.github/workflows/ci.yaml` com `${{ github.sha }}` **intacto**; `gitops-pr/kustomization.yaml` com `newName: ghcr.io/wasp-foundry/dry-run-test`.
- Com `name: Invalid_Name` o formulário recusa (regex).

Confirmar que nada foi criado: `gh api repos/wasp-foundry/dry-run-test` → 404.

- [x] **Step 4: Aparece em `/create`**

`http://localhost:3000/create` lista "Python service (FastAPI)".

- [x] **Step 5: Commit**

```bash
git add idp/templates/python-service/template.yaml idp/app-config.yaml
git commit --message "feat(#101): template python-service registrado no catalog"
```
