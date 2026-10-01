# Bookinfo Seed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Quatro repos públicos na `wasp-foundry` (`productpage`, `details`, `reviews`, `ratings`) com o código do Bookinfo do Istio 1.31.1, CI que publica no GHCR e faz bump em development, entidades do catalog com APIs navegáveis, e as apps rodando em `development` e `production`.

**Architecture:** Assets versionados em `scripts/foundry/assets/bookinfo/` (catalog-info, OpenAPI, CI, manifestos do gitops com placeholder de tag), validados offline por `scripts/foundry/test-bookinfo-assets`; `scripts/foundry/seed-bookinfo` monta cada repo a partir do upstream + assets, cria e protege o repo, e abre um PR único no `gitops`.

**Tech Stack:** bash, git sparse checkout, `gh`, Docker, Kustomize, OpenAPI 3.0 (lint com `redocly/cli`), GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-01-bookinfo-catalog-multi-cluster-design.md` — "Modelo no catalog", "APIs", "Bookinfo no `gitops` (bases)", "`scripts/foundry/seed-bookinfo`", "CI dos repos Bookinfo".

## Global Constraints

- Upstream: `https://github.com/istio/istio.git`, tag `1.31.1`, `samples/bookinfo/src/<svc>/` vira a raiz do repo; `LICENSE` da raiz do istio copiado. Código upstream sem alteração.
- Repos: `wasp-foundry/<svc>`, públicos, `main` protegida (PR obrigatório, `required_approving_review_count: 0`, `enforce_admins: true`).
- Owners: `productpage` → `group:default/team-alpha`; `details`, `reviews`, `ratings` → `group:default/team-beta`. Todos `system: bookinfo`, `dependsOn` nos Resources `development`/`production`.
- APIs: `details-api` (provider `details`), `reviews-api` (provider `reviews`), `ratings-api` (provider `ratings`); `productpage` consome `details-api` e `reviews-api`; `reviews` consome `ratings-api`. `definition: $text: ./openapi.yaml`.
- Porta de todos os containers: `9080`. Probes HTTP em `/health`. Namespace = nome do serviço.
- `productpage`: `DETAILS_HOSTNAME=details.details`, `REVIEWS_HOSTNAME=reviews.reviews`; Service `type: LoadBalancer` porta `9080`. Demais Services `ClusterIP` `9080`.
- `reviews`: Deployments `reviews-v1`/`-v2`/`-v3`, mesma imagem; `ENABLE_RATINGS` `false`/`true`/`true`, `STAR_COLOR` `black`/`black`/`red`, `RATINGS_HOSTNAME=ratings.ratings`; Service `reviews` seleciona os três.
- Imagens: `ghcr.io/wasp-foundry/<svc>:<sha>`; nome no Kustomize `app`; placeholder de tag nos assets: `__IMAGE_TAG__`.
- Pré-requisitos: plano 02 (layout de overlays, ApplicationSet matrix) e plano 03 (System, Resources, descoberta da org).

## Review Focus

- `seed-bookinfo` interrompido no meio (ex.: depois de criar `details`): rodar de novo pula os repos existentes, recupera o SHA inicial de cada um pela API e segue até o PR — testado no Task 5 Step 2.
- `apps/<svc>` já existe no `gitops` (seed rodado depois do merge): o seed não sobrescreve e não abre PR vazio — testado no Task 5 Step 2.
- `--istio-tag` inexistente: falha no clone com mensagem clara, antes de criar qualquer repo — testado no Task 4.
- Liberty (`reviews`) lento para subir: sem `startupProbe` o liveness mata o pod em loop — os manifestos têm `startupProbe` com folga (até 150 s).
- `productpage` com gunicorn de 8 workers gevent: limite de memória baixo causa OOMKill — `limits.memory: 512Mi` e conferência de restarts no Task 5.

---

### Task 1: APIs e `catalog-info.yaml` dos quatro serviços

**Files:**
- Create: `scripts/foundry/test-bookinfo-assets`
- Create: `scripts/foundry/assets/bookinfo/productpage/catalog-info.yaml`
- Create: `scripts/foundry/assets/bookinfo/{details,reviews,ratings}/catalog-info.yaml`
- Create: `scripts/foundry/assets/bookinfo/{details,reviews,ratings}/openapi.yaml`

**Interfaces:**
- Produces: `test-bookinfo-assets` (sem argumentos; exit 0 = tudo válido), estendido nos Tasks 2 e 3.

- [ ] **Step 1: Teste que falha — `scripts/foundry/test-bookinfo-assets`**

```bash
#!/bin/bash
# Validate the Bookinfo seed assets offline: catalog entities and their
# references, OpenAPI definitions, gitops overlays and the CI workflow.
set -e

this_script_path="$(realpath "${0}")"
this_script_directory="${this_script_path%/*}"

assets_directory="${this_script_directory}/assets/bookinfo"
services=(productpage details reviews ratings)
api_providers=(details reviews ratings)

echo "Catalog entities:"

python3 - "${assets_directory}" "${services[@]}" <<'PYTHON'
import pathlib
import sys

import yaml

assets = pathlib.Path(sys.argv[1])
services = sys.argv[2:]
expected_owner = {"productpage": "group:default/team-alpha"}
expected_provides = {"details": ["details-api"], "reviews": ["reviews-api"], "ratings": ["ratings-api"]}
expected_consumes = {"productpage": ["details-api", "reviews-api"], "reviews": ["ratings-api"]}
depends_on = ["resource:default/development", "resource:default/production"]
failed = False


def fail(message):
    global failed
    print(f"FAIL: {message}", file=sys.stderr)
    failed = True


for service in services:
    path = assets / service / "catalog-info.yaml"
    if not path.exists():
        fail(f"{path} missing")
        continue
    documents = [document for document in yaml.safe_load_all(path.read_text()) if document]
    components = [d for d in documents if d["kind"] == "Component"]
    apis = [d for d in documents if d["kind"] == "API"]
    if len(components) != 1:
        fail(f"{service}: expected one Component, got {len(components)}")
        continue
    component = components[0]
    spec = component["spec"]
    annotations = component["metadata"].get("annotations", {})
    checks = {
        "name": component["metadata"]["name"] == service,
        "system": spec.get("system") == "bookinfo",
        "owner": spec.get("owner") == expected_owner.get(service, "group:default/team-beta"),
        "providesApis": spec.get("providesApis", []) == expected_provides.get(service, []),
        "consumesApis": spec.get("consumesApis", []) == expected_consumes.get(service, []),
        "dependsOn": spec.get("dependsOn") == depends_on,
        "project-slug": annotations.get("github.com/project-slug") == f"wasp-foundry/{service}",
        "kubernetes-id": annotations.get("backstage.io/kubernetes-id") == service,
    }
    for check, ok in checks.items():
        if not ok:
            fail(f"{service}: Component {check}")
    if [api["metadata"]["name"] for api in apis] != expected_provides.get(service, []):
        fail(f"{service}: API entities {[api['metadata']['name'] for api in apis]}")
    for api in apis:
        api_spec = api["spec"]
        if api_spec.get("type") != "openapi" or api_spec.get("system") != "bookinfo":
            fail(f"{service}: API {api['metadata']['name']} type/system")
        if api_spec.get("owner") != spec.get("owner"):
            fail(f"{service}: API owner differs from Component owner")
        if api_spec.get("definition") != {"$text": "./openapi.yaml"}:
            fail(f"{service}: API definition must be $text ./openapi.yaml")
        if not (assets / service / "openapi.yaml").exists():
            fail(f"{service}: openapi.yaml missing")
    if not failed:
        print(f"ok: {service}")

sys.exit(1 if failed else 0)
PYTHON

echo ""
echo "OpenAPI definitions:"

for service in "${api_providers[@]}"; do
  docker run \
    --rm \
    --volume "${assets_directory}/${service}:/spec" \
    redocly/cli:latest \
    lint \
    --extends minimal \
    /spec/openapi.yaml > /dev/null
  echo "ok: ${service}/openapi.yaml"
done
```

```bash
chmod +x scripts/foundry/test-bookinfo-assets
```

Run: `scripts/foundry/test-bookinfo-assets`
Expected: `FAIL: .../productpage/catalog-info.yaml missing` (e os demais), exit 1.

- [ ] **Step 2: `productpage/catalog-info.yaml`**

```yaml
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: productpage
  description: Bookinfo product page (Python/Flask) — renders a book with its details and reviews
  annotations:
    github.com/project-slug: wasp-foundry/productpage
    backstage.io/kubernetes-id: productpage
  tags:
    - python
    - flask
  links:
    - url: http://localhost:9081/productpage
      title: development
    - url: http://localhost:9082/productpage
      title: production
spec:
  type: service
  lifecycle: experimental
  owner: group:default/team-alpha
  system: bookinfo
  consumesApis:
    - details-api
    - reviews-api
  dependsOn:
    - resource:default/development
    - resource:default/production
```

- [ ] **Step 3: `details/catalog-info.yaml`**

```yaml
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: details
  description: Bookinfo details service (Ruby) — book metadata such as author, year and ISBN
  annotations:
    github.com/project-slug: wasp-foundry/details
    backstage.io/kubernetes-id: details
  tags:
    - ruby
spec:
  type: service
  lifecycle: experimental
  owner: group:default/team-beta
  system: bookinfo
  providesApis:
    - details-api
  dependsOn:
    - resource:default/development
    - resource:default/production
---
apiVersion: backstage.io/v1alpha1
kind: API
metadata:
  name: details-api
  description: Book details by product id
spec:
  type: openapi
  lifecycle: experimental
  owner: group:default/team-beta
  system: bookinfo
  definition:
    $text: ./openapi.yaml
```

- [ ] **Step 4: `details/openapi.yaml`** (de `details/details.rb`, tag 1.31.1)

```yaml
openapi: 3.0.3
info:
  title: details-api
  version: 1.31.1
  description: Book details served by the Bookinfo details service. Derived from details/details.rb at istio/istio 1.31.1.
  license:
    name: Apache-2.0
    url: https://www.apache.org/licenses/LICENSE-2.0
servers:
  - url: http://details.details:9080
paths:
  /details/{id}:
    get:
      operationId: getDetails
      summary: Details of a book
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: integer
      responses:
        '200':
          description: Book details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/BookDetails'
        '400':
          description: The id is not numeric
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
  /health:
    get:
      operationId: getHealth
      summary: Health check
      responses:
        '200':
          description: The service is healthy
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Health'
components:
  schemas:
    BookDetails:
      type: object
      properties:
        id:
          type: integer
          example: 0
        author:
          type: string
          example: William Shakespeare
        year:
          type: integer
          example: 1595
        type:
          type: string
          example: paperback
        pages:
          type: integer
          example: 200
        publisher:
          type: string
          example: PublisherA
        language:
          type: string
          example: English
        ISBN-10:
          type: string
          example: '1234567890'
        ISBN-13:
          type: string
          example: 123-1234567890
    Error:
      type: object
      properties:
        error:
          type: string
          example: please provide numeric product id
    Health:
      type: object
      properties:
        status:
          type: string
          example: Details is healthy
```

- [ ] **Step 5: `reviews/catalog-info.yaml`**

```yaml
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: reviews
  description: Bookinfo reviews service (Java/Open Liberty) — v1 without ratings, v2 black stars, v3 red stars
  annotations:
    github.com/project-slug: wasp-foundry/reviews
    backstage.io/kubernetes-id: reviews
  tags:
    - java
    - open-liberty
spec:
  type: service
  lifecycle: experimental
  owner: group:default/team-beta
  system: bookinfo
  providesApis:
    - reviews-api
  consumesApis:
    - ratings-api
  dependsOn:
    - resource:default/development
    - resource:default/production
---
apiVersion: backstage.io/v1alpha1
kind: API
metadata:
  name: reviews-api
  description: Book reviews by product id, with star ratings in v2 and v3
spec:
  type: openapi
  lifecycle: experimental
  owner: group:default/team-beta
  system: bookinfo
  definition:
    $text: ./openapi.yaml
```

- [ ] **Step 6: `reviews/openapi.yaml`** (de `LibertyRestEndpoint.java`, tag 1.31.1)

```yaml
openapi: 3.0.3
info:
  title: reviews-api
  version: 1.31.1
  description: Book reviews served by the Bookinfo reviews service. Derived from reviews-application/src/main/java/application/rest/LibertyRestEndpoint.java at istio/istio 1.31.1. The rating object is present only when ENABLE_RATINGS is true (v2, v3).
  license:
    name: Apache-2.0
    url: https://www.apache.org/licenses/LICENSE-2.0
servers:
  - url: http://reviews.reviews:9080
paths:
  /reviews/{productId}:
    get:
      operationId: getReviews
      summary: Reviews of a book
      parameters:
        - name: productId
          in: path
          required: true
          schema:
            type: integer
      responses:
        '200':
          description: Reviews, with ratings when enabled
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Reviews'
  /health:
    get:
      operationId: getHealth
      summary: Health check
      responses:
        '200':
          description: The service is healthy
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Health'
components:
  schemas:
    Reviews:
      type: object
      properties:
        id:
          type: string
          example: '0'
        podname:
          type: string
          example: reviews-v3-6dc9897554-8xrqf
        clustername:
          type: string
          description: Value of CLUSTER_NAME, or the string "null" when unset
          example: 'null'
        reviews:
          type: array
          items:
            $ref: '#/components/schemas/Review'
    Review:
      type: object
      properties:
        reviewer:
          type: string
          example: Reviewer1
        text:
          type: string
          example: An extremely entertaining play by Shakespeare. The slapstick humour is refreshing!
        rating:
          $ref: '#/components/schemas/Rating'
    Rating:
      type: object
      description: Stars and color, or an error when the ratings service is unavailable
      properties:
        stars:
          type: integer
          example: 5
        color:
          type: string
          enum:
            - black
            - red
        error:
          type: string
          example: Ratings service is currently unavailable
    Health:
      type: object
      properties:
        status:
          type: string
          example: Reviews is healthy
```

- [ ] **Step 7: `ratings/catalog-info.yaml`**

```yaml
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: ratings
  description: Bookinfo ratings service (Node.js) — star ratings per reviewer
  annotations:
    github.com/project-slug: wasp-foundry/ratings
    backstage.io/kubernetes-id: ratings
  tags:
    - nodejs
spec:
  type: service
  lifecycle: experimental
  owner: group:default/team-beta
  system: bookinfo
  providesApis:
    - ratings-api
  dependsOn:
    - resource:default/development
    - resource:default/production
---
apiVersion: backstage.io/v1alpha1
kind: API
metadata:
  name: ratings-api
  description: Star ratings by product id
spec:
  type: openapi
  lifecycle: experimental
  owner: group:default/team-beta
  system: bookinfo
  definition:
    $text: ./openapi.yaml
```

- [ ] **Step 8: `ratings/openapi.yaml`** (de `ratings/ratings.js`, tag 1.31.1)

```yaml
openapi: 3.0.3
info:
  title: ratings-api
  version: 1.31.1
  description: Star ratings served by the Bookinfo ratings service (in-memory data, no database). Derived from ratings/ratings.js at istio/istio 1.31.1.
  license:
    name: Apache-2.0
    url: https://www.apache.org/licenses/LICENSE-2.0
servers:
  - url: http://ratings.ratings:9080
paths:
  /ratings/{productId}:
    get:
      operationId: getRatings
      summary: Ratings of a book
      parameters:
        - name: productId
          in: path
          required: true
          schema:
            type: integer
      responses:
        '200':
          description: Ratings per reviewer
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Ratings'
        '400':
          description: The product id is not numeric
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
  /health:
    get:
      operationId: getHealth
      summary: Health check
      responses:
        '200':
          description: The service is healthy
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Health'
components:
  schemas:
    Ratings:
      type: object
      properties:
        id:
          type: integer
          example: 0
        ratings:
          type: object
          properties:
            Reviewer1:
              type: integer
              example: 5
            Reviewer2:
              type: integer
              example: 4
    Error:
      type: object
      properties:
        error:
          type: string
          example: please provide numeric product ID
    Health:
      type: object
      properties:
        status:
          type: string
          example: Ratings is healthy
```

- [ ] **Step 9: Conferir os schemas contra o código** — para cada API, abrir o arquivo upstream citado na `description` (via `gh api "repos/istio/istio/contents/samples/bookinfo/src/<arquivo>?ref=1.31.1" --jq .content | base64 --decode`) e confirmar campos, tipos e códigos de status. Divergência → corrigir o `openapi.yaml`, nunca o upstream.

- [ ] **Step 10: Rodar e commit**

Run: `scripts/foundry/test-bookinfo-assets`
Expected: `ok:` para os quatro serviços e as três OpenAPI.

```bash
docker run --rm --volume "${PWD}:/mnt" --workdir /mnt koalaman/shellcheck:stable scripts/foundry/test-bookinfo-assets
git add scripts/foundry
git commit --message "feat(#105): entidades e OpenAPI do Bookinfo para o seed"
```

### Task 2: Manifestos do `gitops` (bases e overlays)

**Files:**
- Create: `scripts/foundry/assets/bookinfo/gitops/<svc>/base/{deployment,service,kustomization}.yaml` (reviews: `deployment-v1.yaml`, `deployment-v2.yaml`, `deployment-v3.yaml`)
- Create: `scripts/foundry/assets/bookinfo/gitops/<svc>/overlays/{development,production}/kustomization.yaml`
- Modify: `scripts/foundry/test-bookinfo-assets` (bloco novo no fim)

- [ ] **Step 1: Teste que falha** — acrescentar ao fim de `test-bookinfo-assets`:

```bash
echo ""
echo "GitOps overlays:"

render_directory="$(mktemp --directory)"
trap 'rm --recursive --force "${render_directory}"' EXIT

image_tag="0123456789abcdef0123456789abcdef01234567"

for service in "${services[@]}"; do
  cp --recursive "${assets_directory}/gitops/${service}" "${render_directory}/${service}"
  for environment in development production; do
    overlay="${render_directory}/${service}/overlays/${environment}"
    sed --in-place "s|__IMAGE_TAG__|${image_tag}|" "${overlay}/kustomization.yaml"
    manifests="$(kubectl kustomize "${overlay}")"
    expected_image="image: ghcr.io/wasp-foundry/${service}:${image_tag}"
    if [[ "$(grep --count --fixed-strings "${expected_image}" <<< "${manifests}")" -lt 1 ]]; then
      echo "FAIL: ${service}/${environment}: missing ${expected_image}" >&2
      exit 1
    fi
    if grep --quiet 'image: app$' <<< "${manifests}"; then
      echo "FAIL: ${service}/${environment}: image not rewritten" >&2
      exit 1
    fi
    if kubectl --context "k3d-${environment}" version --request-timeout=3s > /dev/null 2>&1; then
      kubectl --context "k3d-${environment}" apply --dry-run=server --filename - <<< "${manifests}" > /dev/null
    fi
  done
  label_count="$(grep --count "backstage.io/kubernetes-id: ${service}" <<< "${manifests}")"
  echo "ok: ${service} (${label_count} kubernetes-id labels)"
done

for service in reviews; do
  manifests="$(kubectl kustomize "${render_directory}/${service}/overlays/development")"
  if [[ "$(grep --count '^kind: Deployment' <<< "${manifests}")" -ne 3 ]]; then
    echo "FAIL: reviews must have 3 Deployments" >&2
    exit 1
  fi
  if [[ "$(grep --count 'value: red' <<< "${manifests}")" -ne 1 ]]; then
    echo "FAIL: exactly one reviews version must use red stars" >&2
    exit 1
  fi
done
echo "ok: reviews v1/v2/v3"

if ! grep --quiet 'type: LoadBalancer' "${assets_directory}/gitops/productpage/base/service.yaml"; then
  echo "FAIL: productpage Service must be LoadBalancer" >&2
  exit 1
fi
echo "ok: productpage Service is LoadBalancer"
```

Run: `scripts/foundry/test-bookinfo-assets`
Expected: Task 1 ok; depois `cp: cannot stat '.../gitops/productpage'`, exit ≠ 0.

- [ ] **Step 2: `productpage`**

`gitops/productpage/base/deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: productpage
  labels:
    app.kubernetes.io/name: productpage
    backstage.io/kubernetes-id: productpage
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: productpage
  template:
    metadata:
      labels:
        app.kubernetes.io/name: productpage
        backstage.io/kubernetes-id: productpage
    spec:
      securityContext:
        runAsNonRoot: true
      containers:
        - name: productpage
          image: app
          ports:
            - name: http
              containerPort: 9080
          env:
            - name: DETAILS_HOSTNAME
              value: details.details
            - name: REVIEWS_HOSTNAME
              value: reviews.reviews
          readinessProbe:
            httpGet:
              path: /health
              port: http
          livenessProbe:
            httpGet:
              path: /health
              port: http
          resources:
            requests:
              cpu: 50m
              memory: 128Mi
            limits:
              memory: 512Mi
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir: {}
```

`gitops/productpage/base/service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: productpage
  labels:
    app.kubernetes.io/name: productpage
    backstage.io/kubernetes-id: productpage
spec:
  type: LoadBalancer
  selector:
    app.kubernetes.io/name: productpage
  ports:
    - name: http
      port: 9080
      targetPort: http
```

- [ ] **Step 3: `details` e `ratings`** — mesmo formato do `productpage`, trocando o nome (`details` / `ratings`) em `metadata.name`, labels, seletor e `containers[0].name`; **sem** `env`, **sem** volume `tmp`; `resources.limits.memory: 128Mi`, `requests.memory: 64Mi`. Service `type: ClusterIP`, porta `9080`, `targetPort: http`. Conteúdo completo de `gitops/details/base/deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: details
  labels:
    app.kubernetes.io/name: details
    backstage.io/kubernetes-id: details
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: details
  template:
    metadata:
      labels:
        app.kubernetes.io/name: details
        backstage.io/kubernetes-id: details
    spec:
      securityContext:
        runAsNonRoot: true
      containers:
        - name: details
          image: app
          ports:
            - name: http
              containerPort: 9080
          readinessProbe:
            httpGet:
              path: /health
              port: http
          livenessProbe:
            httpGet:
              path: /health
              port: http
          resources:
            requests:
              cpu: 20m
              memory: 64Mi
            limits:
              memory: 128Mi
```

`gitops/details/base/service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: details
  labels:
    app.kubernetes.io/name: details
    backstage.io/kubernetes-id: details
spec:
  type: ClusterIP
  selector:
    app.kubernetes.io/name: details
  ports:
    - name: http
      port: 9080
      targetPort: http
```

`ratings`: os dois arquivos acima com `details` → `ratings` (sed: `sed 's/details/ratings/g'`).

- [ ] **Step 4: `reviews`** — `gitops/reviews/base/deployment-v1.yaml` (v2 e v3 iguais trocando `v1` → `v2`/`v3`, `ENABLE_RATINGS` `"false"` → `"true"` em v2 e v3, e `STAR_COLOR` `black` → `red` só em v3):

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: reviews-v1
  labels:
    app.kubernetes.io/name: reviews
    app.kubernetes.io/version: v1
    backstage.io/kubernetes-id: reviews
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: reviews
      app.kubernetes.io/version: v1
  template:
    metadata:
      labels:
        app.kubernetes.io/name: reviews
        app.kubernetes.io/version: v1
        backstage.io/kubernetes-id: reviews
    spec:
      securityContext:
        runAsNonRoot: true
      containers:
        - name: reviews
          image: app
          ports:
            - name: http
              containerPort: 9080
          env:
            - name: SERVICE_VERSION
              value: v1
            - name: ENABLE_RATINGS
              value: "false"
            - name: STAR_COLOR
              value: black
            - name: RATINGS_HOSTNAME
              value: ratings.ratings
          startupProbe:
            httpGet:
              path: /health
              port: http
            periodSeconds: 5
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /health
              port: http
          livenessProbe:
            httpGet:
              path: /health
              port: http
          resources:
            requests:
              cpu: 50m
              memory: 256Mi
            limits:
              memory: 512Mi
          volumeMounts:
            - name: wlp-output
              mountPath: /opt/ol/wlp/output
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: wlp-output
          emptyDir: {}
        - name: tmp
          emptyDir: {}
```

`gitops/reviews/base/service.yaml`: igual ao de `details` com `details` → `reviews` (seletor só `app.kubernetes.io/name: reviews`, que casa os três).

- [ ] **Step 5: Kustomizations** — `gitops/<svc>/base/kustomization.yaml` (reviews lista `deployment-v1.yaml`, `deployment-v2.yaml`, `deployment-v3.yaml`, `service.yaml`):

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
- deployment.yaml
- service.yaml
```

`gitops/<svc>/overlays/development/kustomization.yaml` e `.../production/kustomization.yaml` (idênticos):

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
- ../../base
images:
- name: app
  newName: ghcr.io/wasp-foundry/<svc>
  newTag: __IMAGE_TAG__
```

- [ ] **Step 6: Rodar e commit**

Run: `scripts/foundry/test-bookinfo-assets`
Expected: tudo `ok`, incluindo `ok: reviews v1/v2/v3` e `ok: productpage Service is LoadBalancer`; com os clusters do plano 01 no ar, o server-side dry-run roda nos dois.

```bash
docker run --rm --volume "${PWD}:/mnt" --workdir /mnt koalaman/shellcheck:stable scripts/foundry/test-bookinfo-assets
git add scripts/foundry
git commit --message "feat(#105): manifestos gitops do Bookinfo com overlays por ambiente"
```

### Task 3: CI dos repos Bookinfo

**Files:**
- Create: `scripts/foundry/assets/bookinfo/ci.yaml`
- Modify: `scripts/foundry/test-bookinfo-assets` (bloco novo no fim)

- [ ] **Step 1: Teste que falha** — acrescentar ao fim de `test-bookinfo-assets`:

```bash
echo ""
echo "CI workflow:"

docker run \
  --rm \
  --volume "${assets_directory}:/repo" \
  --workdir /repo \
  rhysd/actionlint:latest \
  -color \
  ci.yaml
if [[ "$(grep --count 'overlays/development' "${assets_directory}/ci.yaml")" -ne 3 ]]; then
  echo "FAIL: ci.yaml must bump apps/<app>/overlays/development" >&2
  exit 1
fi
echo "ok: ci.yaml"
```

Run: `scripts/foundry/test-bookinfo-assets`
Expected: falha no actionlint (arquivo ausente).

- [ ] **Step 2: `scripts/foundry/assets/bookinfo/ci.yaml`** — o `ci.yaml` do template `python-service` (já migrado no plano 02) sem o job `test`, e `build` sem `needs`:

```yaml
name: ci

on:
  push:
    branches: [main]
  pull_request:

jobs:
  build:
    runs-on: ubuntu-24.04
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v7
      - uses: docker/login-action@v4
        if: github.event_name == 'push'
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v7
        with:
          push: ${{ github.event_name == 'push' }}
          tags: ghcr.io/${{ github.repository }}:${{ github.sha }}
          labels: org.opencontainers.image.source=https://github.com/${{ github.repository }}

  bump:
    needs: build
    if: github.event_name == 'push'
    runs-on: ubuntu-24.04
    steps:
      - id: app-token
        uses: actions/create-github-app-token@v3
        with:
          app-id: ${{ vars.FOUNDRY_CI_APP_ID }}
          private-key: ${{ secrets.FOUNDRY_CI_APP_PRIVATE_KEY }}
          owner: ${{ github.repository_owner }}
          repositories: gitops
      - uses: actions/checkout@v7
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
          if [[ ! -d "gitops/apps/${APP}/overlays/development" ]]; then
            echo "apps/${APP} is not in gitops yet (creation PR not merged); the PR already pins this commit's tag"
            echo "skip=true" >> "${GITHUB_OUTPUT}"
            exit 0
          fi
          cd "gitops/apps/${APP}/overlays/development"
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
          git add "apps/${APP}/overlays/development/kustomization.yaml"
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

Diferença deliberada do template: em `pull_request` o `build` roda sem push (prova que o `docker build` — e os testes do `productpage` dentro dele — passam antes do merge).

- [ ] **Step 3: Rodar e commit**

Run: `scripts/foundry/test-bookinfo-assets`
Expected: tudo `ok`, incluindo `ok: ci.yaml`.

```bash
git add scripts/foundry
git commit --message "feat(#105): CI dos repos Bookinfo (build no GHCR e bump em development)"
```

### Task 4: `seed-bookinfo` com `--dry-run`

**Files:**
- Create: `scripts/foundry/seed-bookinfo`

**Interfaces:**
- Consumes: assets dos Tasks 1–3.
- Produces: `seed-bookinfo [--istio-tag <tag>] [--dry-run]`. `--dry-run` monta os quatro repos e o diretório do `gitops` num diretório temporário (impresso e **mantido** para inspeção), roda `docker build` de cada serviço e `kubectl kustomize` de cada overlay; não toca no GitHub.

- [ ] **Step 1: Teste que falha**

Run: `scripts/foundry/seed-bookinfo --dry-run; echo "exit=$?"`
Expected: `No such file or directory`, `exit=127`.

- [ ] **Step 2: `scripts/foundry/seed-bookinfo`**

```bash
#!/bin/bash
# Import the Istio Bookinfo services into the wasp-foundry GitHub org: one public
# repo per service (upstream code + CI + catalog-info.yaml + openapi.yaml), then
# one pull request in wasp-foundry/gitops adding their base and overlays.
# Idempotent: existing repos and existing apps/<service> directories are skipped.
set -e

this_script_path="$(realpath "${0}")"
this_script_directory="${this_script_path%/*}"

assets_directory="${this_script_directory}/assets/bookinfo"
organization="wasp-foundry"
services=(productpage details reviews ratings)

istio_tag="1.31.1"
dry_run="false"

show_usage() {
  cat <<EOF
Usage: ${0##*/} [--istio-tag <tag>] [--dry-run]

  --istio-tag  istio/istio tag to import samples/bookinfo/src from (default: 1.31.1)
  --dry-run    build the repos and the gitops directory locally, docker build each
               service, and touch nothing on GitHub
EOF
}

while [[ "$#" -gt 0 ]]; do
  case "${1}" in
    --istio-tag) istio_tag="${2?}"; shift 2 ;;
    --dry-run) dry_run="true"; shift ;;
    --help) show_usage; exit 0 ;;
    *) echo "Unknown option: ${1}" >&2; show_usage >&2; exit 1 ;;
  esac
done

work_directory="$(mktemp --directory)"
if [[ "${dry_run}" == "false" ]]; then
  trap 'rm --recursive --force "${work_directory}"' EXIT
fi

echo "Fetching samples/bookinfo/src from istio/istio ${istio_tag}..."

if ! git clone \
  --quiet \
  --depth 1 \
  --branch "${istio_tag}" \
  --filter blob:none \
  --sparse \
  https://github.com/istio/istio.git \
  "${work_directory}/istio" 2> "${work_directory}/clone.log"; then
  echo "Could not clone istio/istio at tag ${istio_tag}:" >&2
  cat "${work_directory}/clone.log" >&2
  exit 1
fi

git -C "${work_directory}/istio" sparse-checkout set samples/bookinfo/src

declare -A initial_commits

for service in "${services[@]}"; do
  repository_directory="${work_directory}/repos/${service}"

  if [[ "${dry_run}" == "false" ]] && gh repo view "${organization}/${service}" > /dev/null 2>&1; then
    initial_commits["${service}"]="$(gh api "repos/${organization}/${service}/commits?sha=main&per_page=100" --jq '.[-1].sha')"
    echo "Repository ${organization}/${service} already exists, skipping (initial commit ${initial_commits[${service}]:0:7})"
    continue
  fi

  echo ""
  echo "Building repository ${service}..."

  mkdir --parents "${repository_directory}/.github/workflows"
  cp --recursive "${work_directory}/istio/samples/bookinfo/src/${service}/." "${repository_directory}/"
  cp "${work_directory}/istio/LICENSE" "${repository_directory}/LICENSE"
  cp "${assets_directory}/${service}/catalog-info.yaml" "${repository_directory}/"
  if [[ -f "${assets_directory}/${service}/openapi.yaml" ]]; then
    cp "${assets_directory}/${service}/openapi.yaml" "${repository_directory}/"
  fi
  cp "${assets_directory}/ci.yaml" "${repository_directory}/.github/workflows/ci.yaml"

  git -C "${repository_directory}" init --quiet --initial-branch main
  git -C "${repository_directory}" add --all
  git -C "${repository_directory}" commit \
    --quiet \
    --message "chore: import ${service} from istio/istio ${istio_tag}"
  initial_commits["${service}"]="$(git -C "${repository_directory}" rev-parse HEAD)"

  if [[ "${dry_run}" == "true" ]]; then
    echo "Dry run: docker build ${service}..."
    docker build --quiet --tag "bookinfo-${service}:dry-run" "${repository_directory}" > /dev/null
    echo "ok: ${service} image builds"
    continue
  fi

  gh repo create "${organization}/${service}" \
    --public \
    --description "Bookinfo ${service} (istio/istio ${istio_tag} samples), imported by wasp-idp scripts/foundry/seed-bookinfo"
  git -C "${repository_directory}" remote add origin "git@github.com:${organization}/${service}.git"
  git -C "${repository_directory}" push --quiet --set-upstream origin main

  printf '%s\n' '{"required_status_checks":null,"enforce_admins":true,"required_pull_request_reviews":{"required_approving_review_count":0},"restrictions":null}' \
    | gh api --method PUT "repos/${organization}/${service}/branches/main/protection" --input - > /dev/null
  echo "Repository ${organization}/${service} created and main protected"
done

echo ""
echo "Preparing gitops changes..."

gitops_directory="${work_directory}/gitops"
if [[ "${dry_run}" == "true" ]]; then
  mkdir --parents "${gitops_directory}/apps"
else
  git clone --quiet "git@github.com:${organization}/gitops.git" "${gitops_directory}"
  git -C "${gitops_directory}" switch --quiet --create add-bookinfo
fi

added_services=()

for service in "${services[@]}"; do
  if [[ -d "${gitops_directory}/apps/${service}" ]]; then
    echo "apps/${service} already in gitops, skipping"
    continue
  fi
  cp --recursive "${assets_directory}/gitops/${service}" "${gitops_directory}/apps/${service}"
  for environment in development production; do
    overlay="${gitops_directory}/apps/${service}/overlays/${environment}"
    sed --in-place "s|__IMAGE_TAG__|${initial_commits[${service}]}|" "${overlay}/kustomization.yaml"
    kubectl kustomize "${overlay}" > /dev/null
  done
  added_services+=("${service}")
done

if [[ "${#added_services[@]}" -eq 0 ]]; then
  echo "Nothing to add to gitops."
  exit 0
fi

if [[ "${dry_run}" == "true" ]]; then
  echo ""
  echo "Dry run complete. Repositories and gitops tree kept in ${work_directory}"
  exit 0
fi

git -C "${gitops_directory}" add apps
git -C "${gitops_directory}" commit \
  --quiet \
  --message "apps: add bookinfo (${added_services[*]})"
git -C "${gitops_directory}" push --quiet --force --set-upstream origin add-bookinfo

gh pr create \
  --repo "${organization}/gitops" \
  --base main \
  --head add-bookinfo \
  --title "apps: add bookinfo" \
  --body "Adds ${added_services[*]} (Istio Bookinfo ${istio_tag}) to development and production, pinned to each repo's first commit. Created by wasp-idp scripts/foundry/seed-bookinfo."
```

```bash
chmod +x scripts/foundry/seed-bookinfo
```

- [ ] **Step 3: Tag inexistente**

Run: `scripts/foundry/seed-bookinfo --dry-run --istio-tag 0.0.0-nope; echo "exit=$?"`
Expected: `Could not clone istio/istio at tag 0.0.0-nope:` + erro do git, `exit=1`.

- [ ] **Step 4: Dry run completo** (o build do `reviews` leva minutos — rodar em background)

Run: `scripts/foundry/seed-bookinfo --dry-run > /tmp/seed-dry-run.log 2>&1; echo "exit=$?"; tail -8 /tmp/seed-dry-run.log`
Expected: `ok: <svc> image builds` para os quatro; `Dry run complete. Repositories and gitops tree kept in <dir>`. Inspecionar `<dir>/repos/details` (código upstream + `LICENSE` + `catalog-info.yaml` + `openapi.yaml` + `.github/workflows/ci.yaml`) e `<dir>/gitops/apps/reviews/overlays/production/kustomization.yaml` (tag = SHA local, sem `__IMAGE_TAG__`). Apagar `<dir>` e as imagens `bookinfo-*:dry-run` depois.

- [ ] **Step 5: shellcheck e commit**

```bash
docker run --rm --volume "${PWD}:/mnt" --workdir /mnt koalaman/shellcheck:stable scripts/foundry/seed-bookinfo
git add scripts/foundry/seed-bookinfo
git commit --message "feat(#105): script de seed do Bookinfo na org wasp-foundry"
```

### Task 5: Seed real e deploy nos dois clusters

**Files:** nenhum no repo (efeitos no GitHub e nos clusters).

- [ ] **Step 1: Rodar o seed**

```bash
scripts/foundry/seed-bookinfo > /tmp/seed.log 2>&1; echo "exit=$?"; tail -6 /tmp/seed.log
for service in productpage details reviews ratings; do
  printf '%-12s %s %s\n' "${service}" \
    "$(gh api "repos/wasp-foundry/${service}" --jq .visibility)" \
    "$(gh api "repos/wasp-foundry/${service}/branches/main/protection" --jq '.required_pull_request_reviews.required_approving_review_count')"
done
```

Expected: `exit=0`, URL do PR `wasp-foundry/gitops`; os quatro `public 0`.

- [ ] **Step 2: Idempotência** (antes do merge do PR)

Run: `scripts/foundry/seed-bookinfo 2>&1 | grep -E 'skipping|Nothing|pull'`
Expected: quatro `Repository ... already exists, skipping`; como `apps/<svc>` ainda não está na `main` do `gitops`, ele recria o branch `add-bookinfo` com o mesmo conteúdo (`--force`) e `gh pr create` falha com "a pull request ... already exists" — aceitável e explícito. Depois do merge (Step 4), rodar de novo deve terminar com `Nothing to add to gitops.`

- [ ] **Step 3: CI dos quatro repos (risco 2 do spec)**

```bash
for service in productpage details reviews ratings; do
  run_id="$(gh run list --repo "wasp-foundry/${service}" --limit 1 --json databaseId --jq '.[0].databaseId')"
  gh run watch --repo "wasp-foundry/${service}" "${run_id}" --exit-status > /dev/null 2>&1; echo "${service} exit=$?"
  gh run view --repo "wasp-foundry/${service}" "${run_id}" --json jobs --jq '.jobs[] | "\(.name) \(.conclusion) \(.completedAt)"'
  gh api "orgs/wasp-foundry/packages/container/${service}" --jq .visibility
done
```

Expected: `build` e `bump` verdes nos quatro (`bump` com "is not in gitops yet"); pacotes `public`. Anotar a duração do `build` do `reviews` (registrar no spec, risco 2). Falha por tempo/memória do runner → `superpowers:systematic-debugging`.

- [ ] **Step 4: Merge do PR e deploy**

```bash
gh pr merge add-bookinfo --repo wasp-foundry/gitops --squash --delete-branch
kubectl --context k3d-idp-cluster-zero --namespace argocd annotate applicationset foundry-apps argocd.argoproj.io/refresh=normal --overwrite
for service in productpage details reviews ratings; do
  for environment in development production; do
    for i in $(seq 1 36); do kubectl --context k3d-idp-cluster-zero --namespace argocd get "application/${service}-${environment}" > /dev/null 2>&1 && break; sleep 5; done
    kubectl --context k3d-idp-cluster-zero --namespace argocd wait "application/${service}-${environment}" --for jsonpath='{.status.health.status}'=Healthy --timeout=600s
  done
done
for environment in development production; do
  kubectl --context "k3d-${environment}" get pods --all-namespaces --selector backstage.io/kubernetes-id --output custom-columns=NS:.metadata.namespace,POD:.metadata.name,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount
done
```

Expected: oito Applications `Healthy`; em cada cluster 6 pods (productpage, details, ratings, reviews-v1/v2/v3) `READY true`, `RESTARTS 0` (restart > 0 no `reviews` → aumentar `failureThreshold` do `startupProbe`; no `productpage` → OOM, ver Review Focus).

- [ ] **Step 5: Página de produto pelos dois clusters**

```bash
for port in 9081 9082; do
  page="$(curl --silent --fail "http://localhost:${port}/productpage")"
  printf '%s details=%s reviews=%s\n' "${port}" \
    "$(grep --count 'William Shakespeare' <<< "${page}")" \
    "$(grep --count 'Reviewer1' <<< "${page}")"
done
for i in $(seq 1 12); do curl --silent "http://localhost:9081/productpage" | grep --only-matching --extended-regexp 'color="(black|red)"' | head -1; done | sort | uniq --count
```

Expected: nas duas portas `details=1` (ou mais) e `reviews=1` (ou mais) — prova `productpage → details.details` e `→ reviews.reviews` entre namespaces; no loop, aparecem `color="black"` e `color="red"` (v2 e v3 → `ratings.ratings`), além de respostas sem estrela (v1).

- [ ] **Step 6: Catalog**

```bash
token="$(curl --silent localhost:7007/api/auth/guest/refresh | python3 -c 'import sys,json;print(json.load(sys.stdin)["backstageIdentity"]["token"])')"
for i in $(seq 1 36); do
  count="$(curl --silent --header "Authorization: Bearer ${token}" 'localhost:7007/api/catalog/entities?filter=spec.system=bookinfo' | python3 -c 'import sys,json;print(len(json.load(sys.stdin)))')"
  [[ "${count}" -ge 9 ]] && break
  sleep 10
done
curl --silent --header "Authorization: Bearer ${token}" 'localhost:7007/api/catalog/entities?filter=spec.system=bookinfo' \
  | python3 -c 'import sys,json;[print(e["kind"], e["metadata"]["name"]) for e in json.load(sys.stdin)]'
curl --silent --header "Authorization: Bearer ${token}" localhost:7007/api/catalog/entities/by-name/api/default/reviews-api \
  | python3 -c 'import sys,json;d=json.load(sys.stdin)["spec"]["definition"];print(d[:40])'
```

Expected (em até 6 min, ciclo do provider): 4 `Component`, 3 `API`, 2 `Resource` com `system: bookinfo`; a definição da `reviews-api` começa com `openapi: 3.0.3` (o `$text` foi resolvido).
