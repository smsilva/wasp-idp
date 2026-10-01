# Catalog Model and Org Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O catalog ganha o Domain `bookstore`, o System `bookinfo` e os Resources `development`/`production`, e passa a descobrir sozinho todo `catalog-info.yaml` da org `wasp-foundry` — sobrevivendo ao restart do backend com banco em memória.

**Architecture:** Um arquivo de entidades da plataforma em `idp/catalog/bookinfo.yaml`, registrado como location com regra própria; o módulo `@backstage/plugin-catalog-backend-module-github` (entity provider) no backend, configurado para a org.

**Tech Stack:** Backstage 1.55.3 (novo backend system), `@backstage/plugin-catalog-backend-module-github` `^0.14.0` (versão do manifest da release 1.55.3).

**Spec:** `docs/superpowers/specs/2026-10-01-bookinfo-catalog-multi-cluster-design.md` — "Modelo no catalog" e "Componentes › Backstage".

## Global Constraints

- Domain `bookstore` (owner `group:default/team-alpha`); System `bookinfo` (owner `team-alpha`, `domain: bookstore`); Resources `development` e `production` (`type: kubernetes-cluster`, owner `team-alpha`, `system: bookinfo`).
- Location `../../catalog/bookinfo.yaml` com `rules: [{allow: [Domain, System, Resource]}]` (`Domain` não está no `catalog.rules` global, que não muda).
- Provider: `catalog.providers.github.waspFoundry` — `organization: wasp-foundry`, `catalogPath: /catalog-info.yaml`, `filters.branch: main`, `schedule` a cada 5 min (timeout 3 min, `initialDelay` 15 s). Autentica pela integração GitHub existente (App `wasp-foundry-backstage`).
- Este plano não depende de 00–02.

## Review Focus

- Repo da org sem `catalog-info.yaml` (ex.: `gitops`): o provider ignora sem erro no log — conferir no Task 2.
- `catalog-info.yaml` que referencia entidade inexistente (`dependsOn` de `hello-alpha` antes do Task 1): a entidade entra com relação pendente, sem erro de processamento — por isso o Task 1 vem antes.
- Mesmo repo registrado duas vezes (provider + `catalog:register` do template): o catalog mantém uma entidade só e acusa conflito de location apenas para a segunda origem — conferir no plano 05 com uma app nova.

---

### Task 1: Domain, System e Resources

**Files:**
- Create: `idp/catalog/bookinfo.yaml`
- Modify: `idp/app-config.yaml` (bloco `catalog.locations`, logo após a location de `../../catalog/org.yaml`)

**Interfaces:**
- Produces: `domain:default/bookstore`, `system:default/bookinfo`, `resource:default/development`, `resource:default/production` — referenciados pelos `catalog-info.yaml` do plano 02 (`dependsOn`) e do plano 04.

- [ ] **Step 1: Teste que falha**

```bash
token="$(curl --silent localhost:7007/api/auth/guest/refresh | python3 -c 'import sys,json;print(json.load(sys.stdin)["backstageIdentity"]["token"])')"
for ref in domain/default/bookstore system/default/bookinfo resource/default/development resource/default/production; do
  printf '%s %s\n' "${ref}" "$(curl --silent --output /dev/null --write-out '%{http_code}' --header "Authorization: Bearer ${token}" "localhost:7007/api/catalog/entities/by-name/${ref}")"
done
```

Expected: quatro `404`.

- [ ] **Step 2: `idp/catalog/bookinfo.yaml`**

```yaml
---
# https://backstage.io/docs/features/software-catalog/descriptor-format#kind-domain
apiVersion: backstage.io/v1alpha1
kind: Domain
metadata:
  name: bookstore
  description: Selling books online — catalogue, product pages, reviews and ratings
spec:
  owner: group:default/team-alpha
---
# https://backstage.io/docs/features/software-catalog/descriptor-format#kind-system
apiVersion: backstage.io/v1alpha1
kind: System
metadata:
  name: bookinfo
  description: Istio Bookinfo sample (productpage, details, reviews, ratings), one repo per service in the wasp-foundry org
  links:
    - url: https://github.com/istio/istio/tree/1.31.1/samples/bookinfo
      title: Upstream source (istio/istio 1.31.1)
spec:
  owner: group:default/team-alpha
  domain: bookstore
---
# https://backstage.io/docs/features/software-catalog/descriptor-format#kind-resource
apiVersion: backstage.io/v1alpha1
kind: Resource
metadata:
  name: development
  description: k3d cluster "development" (API 127.0.0.1:6551, apps on localhost:9081), deployed by the cluster-zero ArgoCD
spec:
  type: kubernetes-cluster
  owner: group:default/team-alpha
  system: bookinfo
---
apiVersion: backstage.io/v1alpha1
kind: Resource
metadata:
  name: production
  description: k3d cluster "production" (API 127.0.0.1:6552, apps on localhost:9082), deployed by the cluster-zero ArgoCD
spec:
  type: kubernetes-cluster
  owner: group:default/team-alpha
  system: bookinfo
```

- [ ] **Step 3: Location** — em `idp/app-config.yaml`, logo após o bloco da location `../../catalog/org.yaml`:

```yaml
    # Bookinfo domain, system and the k3d clusters as resources
    - type: file
      target: ../../catalog/bookinfo.yaml
      rules:
        - allow: [Domain, System, Resource]
```

- [ ] **Step 4: Reiniciar e verificar** — parar o backend pelos PIDs de `:3000`/`:7007`, subir de novo (com os `eval` do `backstage-reader` do plano 01, se já existir), esperar `/api/auth/guest/refresh` responder e repetir o Step 1.

Expected: quatro `200`. E a relação:

```bash
curl --silent --header "Authorization: Bearer ${token}" localhost:7007/api/catalog/entities/by-name/system/default/bookinfo \
  | python3 -c 'import sys,json;print(sorted(r["type"]+" "+r["targetRef"] for r in json.load(sys.stdin)["relations"]))'
```

Expected: contém `partOf domain:default/bookstore`, `hasPart resource:default/development`, `hasPart resource:default/production`, `ownedBy group:default/team-alpha`.

- [ ] **Step 5: Commit**

```bash
git add idp/catalog/bookinfo.yaml idp/app-config.yaml
git commit --message "feat(#105): domain bookstore, system bookinfo e clusters como resources"
```

### Task 2: Descoberta automática da org `wasp-foundry`

**Files:**
- Modify: `idp/packages/backend/package.json` (dependência)
- Modify: `idp/packages/backend/src/index.ts`
- Modify: `idp/app-config.yaml` (bloco `catalog`)
- Modify: `idp/yarn.lock`

**Interfaces:**
- Produces: toda entidade em `/catalog-info.yaml` da `main` de qualquer repo da `wasp-foundry` entra no catalog em até 5 min, com `backstage.io/managed-by-location: url:https://github.com/wasp-foundry/<repo>/blob/main/catalog-info.yaml` — o seed do plano 04 depende disso para registrar o Bookinfo.

- [ ] **Step 1: Teste que falha** — com o backend recém-reiniciado (Task 1), a `hello-alpha` registrada por `catalog:register` sumiu:

```bash
curl --silent --output /dev/null --write-out '%{http_code}\n' --header "Authorization: Bearer ${token}" localhost:7007/api/catalog/entities/by-name/component/default/hello-alpha
```

Expected: `404`.

- [ ] **Step 2: Dependência**

```bash
cd idp
node .yarn/releases/yarn-4.4.1.cjs workspace backend add @backstage/plugin-catalog-backend-module-github@^0.14.0
grep plugin-catalog-backend-module-github packages/backend/package.json
```

Expected: `"@backstage/plugin-catalog-backend-module-github": "^0.14.0"`.

- [ ] **Step 3: Backend** — em `idp/packages/backend/src/index.ts`, logo após `backend.add(import('@backstage/plugin-catalog-backend-module-logs'));`:

```typescript
// Discovers catalog-info.yaml in every repo of the wasp-foundry GitHub org
// (catalog.providers.github in app-config.yaml)
backend.add(import('@backstage/plugin-catalog-backend-module-github'));
```

- [ ] **Step 4: Config** — em `idp/app-config.yaml`, dentro de `catalog:` (antes de `rules:`):

```yaml
  providers:
    github:
      waspFoundry:
        organization: wasp-foundry
        catalogPath: /catalog-info.yaml
        filters:
          branch: main
        schedule:
          frequency: { minutes: 5 }
          timeout: { minutes: 3 }
          initialDelay: { seconds: 15 }
```

- [ ] **Step 5: Typecheck e config**

```bash
cd idp
node .yarn/releases/yarn-4.4.1.cjs tsc > /tmp/tsc.log 2>&1; echo "exit=$?"; tail -5 /tmp/tsc.log
node .yarn/releases/yarn-4.4.1.cjs backstage-cli config:check --lax
```

Expected: `exit=0`; config sem erro.

- [ ] **Step 6: Reiniciar e verificar**

```bash
for i in $(seq 1 24); do
  code="$(curl --silent --output /dev/null --write-out '%{http_code}' --header "Authorization: Bearer ${token}" localhost:7007/api/catalog/entities/by-name/component/default/hello-alpha)"
  [[ "${code}" == 200 ]] && break
  sleep 5
done
echo "${code} after $((i * 5))s"
curl --silent --header "Authorization: Bearer ${token}" localhost:7007/api/catalog/entities/by-name/component/default/hello-alpha \
  | python3 -c 'import sys,json;e=json.load(sys.stdin);print(e["metadata"]["annotations"]["backstage.io/managed-by-location"]); print(sorted(r["type"]+" "+r["targetRef"] for r in e["relations"]))'
grep -iE 'github.*(error|warn)' <log do backend> | head -5
```

Expected: `200` em até 2 min; location `url:https://github.com/wasp-foundry/hello-alpha/blob/main/catalog-info.yaml`; relações incluem `dependsOn resource:default/development` e `resource:default/production` (adicionadas no plano 02, Task 3 — se o plano 02 ainda não rodou, só `ownedBy`); nenhum erro do provider (repos sem `catalog-info.yaml`, como `gitops`, são ignorados).

- [ ] **Step 7: Commit**

```bash
git add idp/packages/backend/package.json idp/packages/backend/src/index.ts idp/app-config.yaml idp/yarn.lock
git commit --message "feat(#105): catalog descobre os repos da org wasp-foundry"
```

- [ ] **Step 8: Doc** — em `docs/idp/CLAUDE.md`, seção `## Local backend — gotchas`, substituir o item do `:memory:` por:

```markdown
- The local DB is SQLite `:memory:`, but repos of the `wasp-foundry` org come back on their own: the GitHub entity provider (`catalog.providers.github.waspFoundry`) rescans `/catalog-info.yaml` on `main` every 5 min (first run 15 s after start). Only entities registered by hand from elsewhere vanish on restart.
```

```bash
git add docs/idp/CLAUDE.md
git commit --message "docs(#105): descoberta da org no CLAUDE.md do idp"
```
