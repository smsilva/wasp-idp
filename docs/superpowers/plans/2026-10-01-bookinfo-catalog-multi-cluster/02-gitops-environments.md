# GitOps Environments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Toda app no `wasp-foundry/gitops` passa a ter `base/` + `overlays/{development,production}`; o ApplicationSet `foundry-apps` vira matrix (clusters × apps); o CI faz bump só em development; `promote.yaml` abre PR para production; `hello-alpha` e o template `python-service` migrados.

**Architecture:** Mudança de layout no `gitops` (commit direto, a `main` dele não é protegida), um workflow novo nele, o ApplicationSet reescrito no `wasp-idp`, um PR no repo `hello-alpha` e a migração do template com seus testes.

**Tech Stack:** Kustomize, ArgoCD ApplicationSet (matrix: clusters × git directories), GitHub Actions (`workflow_dispatch`, `yq` e `kustomize` pré-instalados no `ubuntu-24.04`), Backstage scaffolder.

**Spec:** `docs/superpowers/specs/2026-10-01-bookinfo-catalog-multi-cluster-design.md` — "ApplicationSet `foundry-apps`", "`wasp-foundry/gitops`", "Template `python-service` (migração)", "`hello-alpha` (migração)".

## Global Constraints

- Layout: `apps/<app>/base/` (Deployment(s), Service, `kustomization.yaml` sem `images`) e `apps/<app>/overlays/<env>/kustomization.yaml` (`resources: [../../base]`, `images: [{name: app, newName: ghcr.io/wasp-foundry/<app>, newTag: <sha>}]`).
- Todo `kustomization.yaml` no formato do `kustomize edit` (listas sem indentação).
- Application gerada: nome `<app>-<env>`, namespace `<app>`, `project: default`, sync automático `prune`/`selfHeal`, `CreateNamespace=true`, finalizer `resources-finalizer.argocd.argoproj.io`.
- CI das apps: bump só em `apps/<app>/overlays/development`.
- `promote.yaml`: `workflow_dispatch`, input `app`; PR `promote <app> <sha7> to production`, branch `promote-<app>-<sha7>`, com `GITHUB_TOKEN`; recusa app inexistente/inválida e promoção sem mudança.
- Pré-requisito: plano 01 concluído (clusters registrados, contexto corrente `k3d-idp-cluster-zero`).

## Review Focus

- `promote.yaml` com `app` contendo `../` ou `;`: o nome é validado pela mesma regex do template (`^[a-z]([-a-z0-9]{0,38}[a-z0-9])?$`) antes de qualquer uso — testado no Task 1.
- `promote.yaml` rodado duas vezes para a mesma tag: a segunda falha com "production already runs", sem PR — testado no Task 3.
- Branch `promote-<app>-<sha7>` já existe no remoto (PR anterior fechado sem merge): `git push --force` reaproveita; `gh pr create` falharia se já houver PR aberto — a mensagem do `gh` basta.
- Application antiga `hello-alpha` (nome sem sufixo) de um ApplicationSet anterior: não existe mais (cluster-zero foi recriado no plano 01) — conferir no Task 2 que só existem nomes com sufixo.
- Primeiro bump do CI depois da migração: o `kustomize edit` não pode gerar diff de formatação no overlay — conferido no Task 3 pelo diff do commit de bump.

---

### Task 1: `gitops` — layout de ambientes e `promote.yaml`

**Files** (no repo `wasp-foundry/gitops`, clone em diretório temporário):
- Move: `apps/hello-alpha/{deployment,service}.yaml` → `apps/hello-alpha/base/`
- Create: `apps/hello-alpha/base/kustomization.yaml`, `apps/hello-alpha/overlays/{development,production}/kustomization.yaml`
- Delete: `apps/hello-alpha/kustomization.yaml`
- Create: `.github/workflows/promote.yaml`
- Modify: `README.md`

**Interfaces:**
- Produces: `apps/<app>/overlays/<env>` — consumido pelo ApplicationSet (Task 2), pelo CI (Task 3/4) e pelo seed (plano 04).

- [ ] **Step 1: Clonar e ler a tag atual**

```bash
gitops_dir="$(mktemp --directory)"
git clone git@github.com:wasp-foundry/gitops.git "${gitops_dir}"
grep newTag "${gitops_dir}/apps/hello-alpha/kustomization.yaml"
```

Anotar o SHA como `current_tag`.

- [ ] **Step 2: Reestruturar `hello-alpha`**

```bash
cd "${gitops_dir}/apps/hello-alpha"
mkdir --parents base overlays/development overlays/production
git mv deployment.yaml service.yaml base/
git rm --quiet kustomization.yaml
cat > base/kustomization.yaml <<'EOF'
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
- deployment.yaml
- service.yaml
EOF
for env in development production; do
cat > "overlays/${env}/kustomization.yaml" <<EOF
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
- ../../base
images:
- name: app
  newName: ghcr.io/wasp-foundry/hello-alpha
  newTag: ${current_tag}
EOF
done
for env in development production; do kubectl kustomize "overlays/${env}" | grep 'image:'; done
```

Expected: duas linhas `image: ghcr.io/wasp-foundry/hello-alpha:<current_tag>`.

- [ ] **Step 3: Formato estável** — provar que o bump não reformata:

```bash
cp overlays/development/kustomization.yaml /tmp/before.yaml
(cd overlays/development && kustomize edit set image "app=ghcr.io/wasp-foundry/hello-alpha:${current_tag}")
diff /tmp/before.yaml overlays/development/kustomization.yaml && echo "stable"
```

Expected: `stable`. (Se `kustomize` não estiver instalado localmente: `docker run --rm --volume "${PWD}:/w" --workdir /w/overlays/development registry.k8s.io/kustomize/kustomize:v5.6.0 edit set image ...`.)

- [ ] **Step 4: `.github/workflows/promote.yaml`**

```yaml
name: promote

on:
  workflow_dispatch:
    inputs:
      app:
        description: Application directory under apps/
        required: true
        type: string

permissions:
  contents: write
  pull-requests: write

jobs:
  promote:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v7
      - name: Copy development image tag to production
        id: promote
        env:
          APP: ${{ inputs.app }}
        run: |
          if [[ ! "${APP}" =~ ^[a-z]([-a-z0-9]{0,38}[a-z0-9])?$ ]]; then
            echo "Invalid app name: ${APP}" >&2
            exit 1
          fi
          overlays="apps/${APP}/overlays"
          if [[ ! -f "${overlays}/development/kustomization.yaml" || ! -f "${overlays}/production/kustomization.yaml" ]]; then
            echo "apps/${APP} has no development/production overlays" >&2
            exit 1
          fi
          query='.images[] | select(.name == "app")'
          image_name="$(yq "${query} | .newName" "${overlays}/development/kustomization.yaml")"
          development_tag="$(yq "${query} | .newTag" "${overlays}/development/kustomization.yaml")"
          production_tag="$(yq "${query} | .newTag" "${overlays}/production/kustomization.yaml")"
          if [[ "${development_tag}" == "${production_tag}" ]]; then
            echo "production already runs ${development_tag}; nothing to promote" >&2
            exit 1
          fi
          cd "${overlays}/production"
          kustomize edit set image "app=${image_name}:${development_tag}"
          echo "tag=${development_tag}" >> "${GITHUB_OUTPUT}"
      - name: Open pull request
        env:
          APP: ${{ inputs.app }}
          TAG: ${{ steps.promote.outputs.tag }}
          GH_TOKEN: ${{ github.token }}
        run: |
          branch="promote-${APP}-${TAG::7}"
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git switch --create "${branch}"
          git add "apps/${APP}/overlays/production/kustomization.yaml"
          git commit --message "apps(${APP}): promote ${TAG::7} to production"
          git push --force origin "${branch}"
          gh pr create \
            --base main \
            --head "${branch}" \
            --title "promote ${APP} ${TAG::7} to production" \
            --body "Promotes \`${APP}\` image \`${TAG}\` from development to production. Merging deploys it to the production cluster."
```

- [ ] **Step 5: actionlint**

```bash
docker run --rm --volume "${gitops_dir}:/repo" --workdir /repo rhysd/actionlint:latest -color .github/workflows/promote.yaml
```

Expected: sem saída.

- [ ] **Step 6: README** — substituir o corpo de `README.md` do `gitops` por:

```markdown
# gitops

Desired state of every application in the `wasp-foundry` org, deployed by the `foundry-apps` ApplicationSet of the wasp-idp cluster-zero.

- `apps/<app>/base/` — Kustomize base (Deployment, Service). Image name `app`, no tag.
- `apps/<app>/overlays/development/` and `overlays/production/` — the image tag per environment. One ArgoCD `Application` per app and environment (`<app>-development`, `<app>-production`).
- New apps arrive by pull request from Backstage (or `scripts/foundry/seed-bookinfo`), with the first commit's tag in both overlays.
- Each app's CI bumps `overlays/development` with a direct commit to `main`. Production changes only by pull request: run the `promote` workflow (`gh workflow run promote.yaml --repo wasp-foundry/gitops -f app=<app>`) and merge the PR it opens.
```

- [ ] **Step 7: Ligar a criação de PR pelo Actions e enviar**

```bash
printf '{"default_workflow_permissions":"read","can_approve_pull_request_reviews":true}\n' > /tmp/workflow-permissions.json
gh api --method PUT repos/wasp-foundry/gitops/actions/permissions/workflow --input /tmp/workflow-permissions.json
gh api repos/wasp-foundry/gitops/actions/permissions/workflow --jq .can_approve_pull_request_reviews
git -C "${gitops_dir}" add --all
git -C "${gitops_dir}" commit --message "chore: per-environment overlays and promote workflow"
git -C "${gitops_dir}" push
```

Expected: `true`; push aceito.

- [ ] **Step 8: Validação de entrada do `promote`**

```bash
gh workflow run promote.yaml --repo wasp-foundry/gitops -f app='../x'
sleep 10
run_id="$(gh run list --repo wasp-foundry/gitops --workflow promote.yaml --limit 1 --json databaseId --jq '.[0].databaseId')"
gh run watch --repo wasp-foundry/gitops "${run_id}" --exit-status; echo "exit=$?"
gh run view --repo wasp-foundry/gitops "${run_id}" --log | grep 'Invalid app name'
gh pr list --repo wasp-foundry/gitops --state open
```

Expected: run falha; log contém `Invalid app name: ../x`; nenhum PR aberto. Manter `gitops_dir` para o Task 3; nenhum commit no `wasp-idp` neste task.

### Task 2: ApplicationSet matrix

**Files:**
- Modify: `scripts/cluster-zero/assets/foundry-appset.yaml` (reescrita)
- Modify: `scripts/cluster-zero/install-foundry-appset` (mensagem)
- Modify: `scripts/cluster-zero/up` (chamar `install-foundry-appset` no fim)

**Interfaces:**
- Consumes: Secrets de cluster com label `env` (plano 01); layout do Task 1.
- Produces: Applications `<app>-development` / `<app>-production`.

- [ ] **Step 1: Teste que falha**

Run: `kubectl --context k3d-idp-cluster-zero --namespace argocd get applications --output name`
Expected: vazio (nenhum ApplicationSet no cluster-zero recriado).

- [ ] **Step 2: `assets/foundry-appset.yaml`**

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: foundry-apps
  namespace: argocd
spec:
  goTemplate: true
  goTemplateOptions: ["missingkey=error"]
  generators:
    - matrix:
        generators:
          - clusters:
              selector:
                matchExpressions:
                  - key: env
                    operator: In
                    values:
                      - development
                      - production
          - git:
              repoURL: https://github.com/wasp-foundry/gitops.git
              revision: main
              directories:
                - path: apps/*
  template:
    metadata:
      name: '{{ .path.basename }}-{{ .name }}'
      finalizers:
        - resources-finalizer.argocd.argoproj.io
    spec:
      project: default
      source:
        repoURL: https://github.com/wasp-foundry/gitops.git
        targetRevision: main
        path: '{{ .path.path }}/overlays/{{ .name }}'
      destination:
        server: '{{ .server }}'
        namespace: '{{ .path.basename }}'
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
        syncOptions:
          - CreateNamespace=true
```

- [ ] **Step 3: Mensagem do `install-foundry-appset`** — trocar `echo "Applying ApplicationSet foundry-apps (wasp-foundry/gitops apps/*)..."` por `echo "Applying ApplicationSet foundry-apps (wasp-foundry/gitops apps/* x development, production)..."`. Em `up`, acrescentar `install-foundry-appset` como última linha antes de `verify`.

- [ ] **Step 4: Aplicar e verificar**

```bash
scripts/cluster-zero/install-foundry-appset
for env in development production; do
  kubectl --context k3d-idp-cluster-zero --namespace argocd wait "application/hello-alpha-${env}" --for jsonpath='{.status.health.status}'=Healthy --timeout=300s
  kubectl --context "k3d-${env}" --namespace hello-alpha get deployment hello-alpha --output jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
done
kubectl --context k3d-idp-cluster-zero --namespace argocd get applications --output name
```

Expected: as duas `Healthy`; imagem `ghcr.io/wasp-foundry/hello-alpha:<current_tag>` nos dois clusters; só `hello-alpha-development` e `hello-alpha-production` listadas.

- [ ] **Step 5: shellcheck e commit**

```bash
docker run --rm --volume "${PWD}:/mnt" --workdir /mnt koalaman/shellcheck:stable scripts/cluster-zero/install-foundry-appset scripts/cluster-zero/up
git add scripts/cluster-zero/assets/foundry-appset.yaml scripts/cluster-zero/install-foundry-appset scripts/cluster-zero/up
git commit --message "feat(#105): ApplicationSet foundry-apps em matrix clusters x apps"
```

### Task 3: `hello-alpha` — CI em development e promoção ponta a ponta

**Files** (no repo `wasp-foundry/hello-alpha`, por PR):
- Modify: `.github/workflows/ci.yaml` (job `bump`)
- Modify: `catalog-info.yaml` (`dependsOn`)

- [ ] **Step 1: Branch e edição**

```bash
app_dir="$(mktemp --directory)"
git clone git@github.com:wasp-foundry/hello-alpha.git "${app_dir}"
git -C "${app_dir}" switch --create environments
```

Em `.github/workflows/ci.yaml`, job `bump`, step `Set image tag`: trocar `gitops/apps/${APP}` por `gitops/apps/${APP}/overlays/development` nas duas ocorrências (o teste `-d` e o `cd`), e a mensagem `apps/${APP} is not in gitops yet` permanece. No step `Commit and push`, trocar `git add "apps/${APP}/kustomization.yaml"` por `git add "apps/${APP}/overlays/development/kustomization.yaml"`.

Em `catalog-info.yaml`, acrescentar ao fim de `spec:`:

```yaml
  dependsOn:
    - resource:default/development
    - resource:default/production
```

Mudar a saudação para provar o fluxo: em `app/main.py` e `tests/test_main.py`, `"hello again"` → `"hello environments"`.

- [ ] **Step 2: actionlint e PR**

```bash
docker run --rm --volume "${app_dir}:/repo" --workdir /repo rhysd/actionlint:latest -color .github/workflows/ci.yaml
git -C "${app_dir}" commit --all --message "feat: deploy through development and production overlays"
git -C "${app_dir}" push --set-upstream origin environments
gh pr create --repo wasp-foundry/hello-alpha --head environments --base main --title "feat: deploy through development and production overlays" --body "Bump only the development overlay; production changes through the gitops promote workflow."
```

Esperar o CI do PR (`test`) verde e fazer merge: `gh pr merge environments --repo wasp-foundry/hello-alpha --squash --delete-branch`.

- [ ] **Step 3: Development muda, production não**

```bash
merge_sha="$(gh api repos/wasp-foundry/hello-alpha/commits/main --jq .sha)"
run_id="$(gh run list --repo wasp-foundry/hello-alpha --commit "${merge_sha}" --limit 1 --json databaseId --jq '.[0].databaseId')"
gh run watch --repo wasp-foundry/hello-alpha "${run_id}" --exit-status
bump_sha="$(gh api repos/wasp-foundry/gitops/commits --jq '.[0].sha')"
gh api "repos/wasp-foundry/gitops/commits/${bump_sha}" --jq '.commit.message, (.files[] | .filename, .patch)'
kubectl --context k3d-idp-cluster-zero --namespace argocd annotate application hello-alpha-development argocd.argoproj.io/refresh=normal --overwrite
kubectl --context k3d-development --namespace hello-alpha rollout status deployment/hello-alpha --timeout=300s
for env in development production; do kubectl --context "k3d-${env}" --namespace hello-alpha get deployment hello-alpha --output jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'; done
```

Expected: commit `apps(hello-alpha): deploy <merge_sha7>` alterando **só** `apps/hello-alpha/overlays/development/kustomization.yaml`, e o patch só troca a linha `newTag` (sem reindentação); development com `:<merge_sha>`, production ainda com `:<current_tag>`.

- [ ] **Step 4: Promover**

```bash
gh workflow run promote.yaml --repo wasp-foundry/gitops -f app=hello-alpha
sleep 10
run_id="$(gh run list --repo wasp-foundry/gitops --workflow promote.yaml --limit 1 --json databaseId --jq '.[0].databaseId')"
gh run watch --repo wasp-foundry/gitops "${run_id}" --exit-status
gh pr list --repo wasp-foundry/gitops --state open --json number,title,headRefName
```

Expected: PR `promote hello-alpha <merge_sha7> to production`, branch `promote-hello-alpha-<merge_sha7>`, diff só em `overlays/production`. Merge: `gh pr merge <número> --repo wasp-foundry/gitops --squash --delete-branch`.

```bash
kubectl --context k3d-idp-cluster-zero --namespace argocd annotate application hello-alpha-production argocd.argoproj.io/refresh=normal --overwrite
kubectl --context k3d-production --namespace hello-alpha rollout status deployment/hello-alpha --timeout=300s
kubectl --context k3d-production --namespace hello-alpha get deployment hello-alpha --output jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
```

Expected: production com `:<merge_sha>`.

- [ ] **Step 5: Promoção sem mudança é recusada**

```bash
gh workflow run promote.yaml --repo wasp-foundry/gitops -f app=hello-alpha
sleep 10
run_id="$(gh run list --repo wasp-foundry/gitops --workflow promote.yaml --limit 1 --json databaseId --jq '.[0].databaseId')"
gh run watch --repo wasp-foundry/gitops "${run_id}" --exit-status; echo "exit=$?"
gh run view --repo wasp-foundry/gitops "${run_id}" --log | grep 'already runs'
gh pr list --repo wasp-foundry/gitops --state open
```

Expected: run falha; log `production already runs <merge_sha>`; nenhum PR aberto. Remover `app_dir` e `gitops_dir`. Nenhum commit no `wasp-idp`.

### Task 4: Template `python-service` migrado

**Files:**
- Move: `idp/templates/python-service/gitops/{deployment,service}.yaml` → `idp/templates/python-service/gitops/base/`
- Create: `idp/templates/python-service/gitops/base/kustomization.yaml`
- Create: `idp/templates/python-service/gitops/overlays/{development,production}/kustomization.yaml`
- Delete: `idp/templates/python-service/gitops/kustomization.yaml`
- Modify: `idp/templates/python-service/content/.github/workflows/ci.yaml` (job `bump`)
- Modify: `idp/templates/python-service/content/catalog-info.yaml`
- Modify: `idp/templates/python-service/test-render`
- Modify: `idp/templates/python-service/test-dry-run`

**Interfaces:**
- Consumes: `values.name`, `values.imageTag` (inalterados no `template.yaml`; `fetch:template` de `./gitops` renderiza a árvore inteira em `./gitops-pr`, e `publish:github:pull-request` grava em `apps/<name>/`).

- [ ] **Step 1: Teste que falha — `test-render`** — substituir o bloco que vai de `mkdir --parents "${render_directory}/gitops"` até `manifests="$(kubectl kustomize "${render_directory}/gitops")"` por:

```bash
while IFS= read -r file; do
  relative_path="${file#"${this_script_directory}/gitops/"}"
  mkdir --parents "${render_directory}/gitops/${relative_path%/*}"
  render "${file}" "${render_directory}/gitops/${relative_path}"
done < <(find "${this_script_directory}/gitops" -type f -name '*.yaml')

render \
  "${this_script_directory}/content/catalog-info.yaml" \
  "${render_directory}/catalog-info.yaml"

for environment in development production; do
  if [[ ! -f "${render_directory}/gitops/overlays/${environment}/kustomization.yaml" ]]; then
    echo "FAIL: missing overlays/${environment}/kustomization.yaml" >&2
    exit 1
  fi
done

manifests="$(kubectl kustomize "${render_directory}/gitops/overlays/development")"
production_manifests="$(kubectl kustomize "${render_directory}/gitops/overlays/production")"

if [[ "${manifests}" != "${production_manifests}" ]]; then
  echo "FAIL: development and production overlays must render the same manifests at creation" >&2
  diff <(echo "${manifests}") <(echo "${production_manifests}") >&2
  exit 1
fi
echo "ok: development and production overlays render the same manifests"
```

E acrescentar às checagens do `catalog-info.yaml` no fim:

```bash
grep --quiet "resource:default/development" "${render_directory}/catalog-info.yaml"
grep --quiet "resource:default/production" "${render_directory}/catalog-info.yaml"
```

Run: `idp/templates/python-service/test-render`
Expected: FAIL `missing overlays/development/kustomization.yaml`.

- [ ] **Step 2: Arquivos do gitops do template**

```bash
cd idp/templates/python-service/gitops
mkdir --parents base overlays/development overlays/production
git mv deployment.yaml service.yaml base/
git rm --quiet kustomization.yaml
```

`base/kustomization.yaml`:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
- deployment.yaml
- service.yaml
```

`overlays/development/kustomization.yaml` e `overlays/production/kustomization.yaml` (idênticos):

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
- ../../base
images:
- name: app
  newName: ghcr.io/wasp-foundry/${{ values.name }}
  newTag: ${{ values.imageTag }}
```

- [ ] **Step 3: `catalog-info.yaml` do template** — acrescentar ao fim de `spec:`:

```yaml
  dependsOn:
    - resource:default/development
    - resource:default/production
```

- [ ] **Step 4: Rodar `test-render`**

Run: `idp/templates/python-service/test-render`
Expected: todas as linhas `ok:` (incluindo `development and production overlays render the same manifests`) e `ok: server-side dry-run` (o contexto corrente é o cluster-zero; o dry-run só valida o schema).

- [ ] **Step 5: CI do template** — em `content/.github/workflows/ci.yaml`, job `bump`, a mesma edição do Task 3 Step 1 (`gitops/apps/${APP}` → `gitops/apps/${APP}/overlays/development` no teste `-d` e no `cd`; `git add "apps/${APP}/overlays/development/kustomization.yaml"`). Depois:

```bash
docker run --rm --volume "${PWD}/idp/templates/python-service/content:/repo" --workdir /repo rhysd/actionlint:latest -color .github/workflows/ci.yaml
grep --count 'overlays/development' idp/templates/python-service/content/.github/workflows/ci.yaml
```

Expected: actionlint sem saída; contagem `3`.

- [ ] **Step 6: `test-dry-run` — caso novo.** Os `CASES` atuais são de injeção; este é uma função à parte, chamada em `main()` antes do `sys.exit`:

```python
def overlays_receive_the_tag(backend_url, token, template, contents):
    values = {"name": "overlay-test", "description": "ok", "owner": "group:default/team-alpha"}
    result, status = dry_run(backend_url, token, template, contents, values)
    if status is not None:
        return False
    files = {item["path"]: base64.b64decode(item["base64Content"]).decode() for item in result["directoryContents"]}
    tags = []
    for environment in ("development", "production"):
        path = f"gitops-pr/overlays/{environment}/kustomization.yaml"
        if path not in files:
            return False
        image = yaml.safe_load(files[path])["images"][0]
        if image["newName"] != "ghcr.io/wasp-foundry/overlay-test":
            return False
        tags.append(image["newTag"])
    catalog_info = yaml.safe_load(files["catalog-info.yaml"])
    return tags[0] == tags[1] and catalog_info["spec"].get("dependsOn") == [
        "resource:default/development",
        "resource:default/production",
    ]
```

Em `main()`, antes de `sys.exit(...)`:

```python
    if overlays_receive_the_tag(arguments.backend_url, token, template, contents):
        print("ok: both overlays receive the image tag; catalog-info depends on both clusters")
    else:
        print("FAIL: overlays or dependsOn", file=sys.stderr)
        failed = True
```

Run (Backstage no ar): `idp/templates/python-service/test-dry-run`
Expected: as três linhas de injeção `ok` + `ok: both overlays receive the image tag; ...`. Provar que o caso falha sem a migração: `mv idp/templates/python-service/gitops/overlays /tmp/overlays-bak`, rodar → `FAIL: overlays or dependsOn`, `mv /tmp/overlays-bak idp/templates/python-service/gitops/overlays`, rodar de novo → `ok`.

- [ ] **Step 7: Commit**

```bash
git add idp/templates/python-service
git commit --message "feat(#105): template python-service com overlays development e production"
```
