# Bookinfo Catalog and Multi-Cluster Deploy — Design

Issue [#105](https://github.com/smsilva/wasp-idp/issues/105). Parte do fluxo entregue na [#101](https://github.com/smsilva/wasp-idp/issues/101) (template `python-service`, org `wasp-foundry`, repo `wasp-foundry/gitops`, ApplicationSet `foundry-apps`).

## Contexto

O catalog do Backstage em `idp/` tem só o exemplo padrão (System `examples`, `example-website`, `example-grpc-api`), os times `team-alpha`/`team-beta` e a `hello-alpha` criada na aceitação da #101. Nada exercita Domain, System, API com definição navegável, Resource nem relações entre times — a interface não tem o que mostrar.

O deploy da #101 tem um ambiente só: o ApplicationSet `foundry-apps` no k3d `idp-cluster-zero` faz deploy no próprio cluster, a partir de `apps/<app>/` plano no `gitops`.

Achado durante o design: o banco do Backstage local é SQLite em memória (`backend.database.connection: ':memory:'` em `idp/app-config.yaml`). Tudo que entra por `catalog:register` — a `hello-alpha`, inclusive — some quando o backend reinicia.

Os plugins de frontend necessários já estão instalados e são descobertos pelo novo frontend system: `@backstage/plugin-api-docs` (aba Definition), `@backstage/plugin-catalog-graph`, `@backstage/plugin-org`, `@backstage/plugin-kubernetes`.

## Objetivo

Abrir o Domain `bookstore` no Backstage, descer pelo System `bookinfo` até Components com pods rodando em dois clusters (`development` e `production`), navegar pelas APIs (quem fornece, quem consome, definição OpenAPI) e acessar a aplicação de verdade pelo navegador — com código real (Bookinfo do Istio), não esqueletos.

## Decisões

| Decisão | Escolha | Descartado |
|---|---|---|
| Aplicação de exemplo | Bookinfo do Istio, tag `1.31.1`, `samples/bookinfo/src/` | `helloworld`/`httpbin` (spec futuro); exemplos escritos do zero |
| Imagens | Build pelo CI de cada repo, GHCR | Imagens upstream `docker.io/istio/examples-bookinfo-*`; misto |
| Criação dos repos | Script de seed único (`scripts/foundry/seed-bookinfo`) | Template "import existing service" no Backstage; monorepo `wasp-foundry/bookinfo` |
| Escopo | Só Bookinfo | Bookinfo + `helloworld` + `httpbin` |
| Definição das APIs | OpenAPI 3 mínima por API, escrita a partir do código, no repo do provider | Placeholder; `swagger.yaml` upstream do `productpage` |
| Onde mora `catalog-info.yaml` | No repo de cada serviço; Domain/System/Resources em `idp/catalog/` | Tudo centralizado em `idp/catalog/bookinfo.yaml` |
| Clusters | `development` e `production` (k3d, 1 server cada) gerenciados pelo ArgoCD central do `idp-cluster-zero` | Um ArgoCD por cluster |
| Fluxo existente | Migrar template `python-service` e `hello-alpha` para o modelo novo | Dois modelos lado a lado |
| Promoção | `workflow_dispatch` `promote.yaml` no `gitops` abre PR para production | CI de cada app abre PR de production a cada build |
| Registro no catalog | Descoberta automática da org (`plugin-catalog-backend-module-github`) | `catalog:register`/locations em `app-config.yaml` por repo |
| Acesso externo | Porta do host → loadbalancer do k3d → Service `LoadBalancer` do `productpage` | `port-forward`; ingress |

## Arquitetura

```
wasp-idp (este repo)
  scripts/foundry/seed-bookinfo ──► wasp-foundry/{productpage,details,reviews,ratings}
     │  código de istio/istio@1.31.1 + CI + catalog-info.yaml + openapi.yaml + LICENSE
     └─► PR em wasp-foundry/gitops: apps/<svc>/{base,overlays/development,overlays/production}

wasp-foundry/<svc> merge na main
  └─ CI: docker build → ghcr.io/wasp-foundry/<svc>:<sha> → bump em overlays/development
wasp-foundry/gitops  promote.yaml (workflow_dispatch, app=<svc>)
  └─ PR "promote <svc> <sha7> to production" → merge = deploy em production

Rede Docker k3d-idp
  idp-cluster-zero (3 servers, API 6550, 9080/9443 → ArgoCD)
    └─ ArgoCD + ApplicationSet foundry-apps (matrix: clusters[env] × git apps/*)
         ├─► development (1 server, API 6551, host 9081 → lb 9080)
         └─► production  (1 server, API 6552, host 9082 → lb 9080)

Backstage (yarn start, local)
  ├─ catalog: provider github (org wasp-foundry, /catalog-info.yaml) + idp/catalog/*.yaml
  └─ kubernetes: clusters development e production (ServiceAccount read-only em cada)
```

## Modelo no catalog

```
Domain  bookstore                       owner team-alpha
└─ System  bookinfo                     owner team-alpha   domain bookstore
   ├─ Component productpage  service    owner team-alpha   consumesApis [details-api, reviews-api]
   ├─ Component details      service    owner team-beta    providesApis [details-api]
   ├─ Component reviews      service    owner team-beta    providesApis [reviews-api]  consumesApis [ratings-api]
   ├─ Component ratings      service    owner team-beta    providesApis [ratings-api]
   ├─ API details-api / reviews-api / ratings-api   type openapi, definition $text ./openapi.yaml
   └─ Resource development / production  type kubernetes-cluster   owner team-alpha
```

- Cada Component declara `system: bookinfo`, `dependsOn: [resource:default/development, resource:default/production]` e as annotations `github.com/project-slug: wasp-foundry/<svc>` e `backstage.io/kubernetes-id: <svc>`.
- Cada API declara `system: bookinfo` e o mesmo owner do Component que a fornece.
- `catalog-info.yaml` de cada repo contém o Component e, nos três backends, a API que ele fornece (documento YAML múltiplo). O `openapi.yaml` fica ao lado, na raiz do repo.
- `idp/catalog/bookinfo.yaml` (novo, registrado em `catalog.locations` com `allow: [Domain, System, Resource]`): Domain, System e os dois Resources.

### APIs (OpenAPI 3.0, mínimas, derivadas do código da tag `1.31.1`)

| API | Endpoints | Fonte |
|---|---|---|
| `details-api` | `GET /details/{id}` → `{id, author, year, type, pages, publisher, language, ISBN-10, ISBN-13}`; `GET /health` | `details/details.rb` |
| `reviews-api` | `GET /reviews/{productId}` → `{id, podname, clustername, reviews[{reviewer, text, rating{stars, color}}]}`; `GET /health` | `reviews/reviews-application/.../LibertyRestEndpoint.java` |
| `ratings-api` | `GET /ratings/{productId}` → `{id, ratings{Reviewer1, Reviewer2}}`; `GET /health` | `ratings/ratings.js` |

Os schemas são conferidos contra o código ao escrever, não copiados de documentação.

## Componentes

### Clusters (`scripts/cluster-zero/`)

| Cluster | Servers | API | Porta do host | Papel |
|---|---|---|---|---|
| `idp-cluster-zero` | 3 | 6550 | `9080`/`9443` → ArgoCD | gestão: só ArgoCD, sem apps |
| `development` | 1 | 6551 | `9081` → lb `9080` | apps, overlay `development` |
| `production` | 1 | 6552 | `9082` → lb `9080` | apps, overlay `production` |

- `cluster-create` ganha opções longas: `--name`, `--servers`, `--api-port`, `--network`, `--app-port` (mapeia `<app-port>:9080@loadbalancer`; ausente no cluster-zero, que mantém os `9080:80`/`9443:443` do ArgoCD). Padrão do loadbalancer da skill `kubernetes` (`references/k3d.md`): Service `type: LoadBalancer` na porta mapeada é alcançado pelo host via klipper-lb.
- Todos os clusters entram na rede Docker `k3d-idp` (k3d não muda a rede de cluster existente: o `idp-cluster-zero` atual é recriado — é descartável, tudo que roda nele vem do `gitops`).
- `register-clusters` (novo): para `development` e `production`, cria um ServiceAccount `argocd-manager` com `cluster-admin` no cluster de destino e um Secret de cluster do ArgoCD no `idp-cluster-zero` com `server: https://k3d-<nome>-server-0:6443` (endereço na rede `k3d-idp`), token e CA do ServiceAccount, e label `env=<nome>`.
- `install-foundry-appset` aplica o ApplicationSet novo (abaixo).
- `backstage-reader` ganha `--cluster <nome>` (contexto `k3d-<nome>`) e imprime `export K8S_<NOME>_TOKEN=...` / `export K8S_<NOME>_CA=...`.
- `up` passa a criar os três clusters, instalar o ArgoCD no cluster-zero, registrar os dois de destino e aplicar o ApplicationSet. Cria no Docker a rede `k3d-idp` se não existir.

### ApplicationSet `foundry-apps`

Gerador `matrix`: `clusters` (selector `matchExpressions: env In [development, production]`) × `git` directories `apps/*` de `https://github.com/wasp-foundry/gitops.git`. Template: nome `{{ .path.basename }}-{{ .name }}`, `path: {{ .path.path }}/overlays/{{ .name }}`, `destination.server: {{ .server }}`, `namespace: {{ .path.basename }}`, `project: default`, sync automático com `prune`/`selfHeal`, `CreateNamespace=true`, finalizer `resources-finalizer.argocd.argoproj.io`. `goTemplate: true`, `missingkey=error`.

### `wasp-foundry/gitops`

```
apps/<app>/
├── base/                     Deployment(s), Service, kustomization.yaml (image name "app", sem tag)
└── overlays/
    ├── development/kustomization.yaml   resources [../../base] · images app → ghcr.io/wasp-foundry/<app>:<sha>
    └── production/kustomization.yaml    resources [../../base] · images app → ghcr.io/wasp-foundry/<app>:<sha>
```

Formato YAML de todos os `kustomization.yaml`: o que o `kustomize edit` escreve (listas sem indentação), para o primeiro bump não gerar commit de reformatação (lição da #101).

`promote.yaml` (novo, `.github/workflows/`): `workflow_dispatch` com input `app`; lê a tag de `apps/<app>/overlays/development/kustomization.yaml`, aplica com `kustomize edit set image` em `overlays/production`, cria branch `promote-<app>-<sha7>` e abre PR `promote <app> <sha7> to production` com o `GITHUB_TOKEN` (`permissions: contents: write, pull-requests: write`). Falha com mensagem clara se `apps/<app>` não existe ou se production já tem a tag. Pré-requisito: no repo `gitops`, Actions → "Allow GitHub Actions to create and approve pull requests" ligado (`PUT /repos/wasp-foundry/gitops/actions/permissions/workflow` com `can_approve_pull_request_reviews: true`).

### Bookinfo no `gitops` (bases)

| App | Base |
|---|---|
| `productpage` | Deployment (porta 9080, env `DETAILS_HOSTNAME=details.details`, `REVIEWS_HOSTNAME=reviews.reviews`), Service **`type: LoadBalancer`** porta 9080 |
| `details` | Deployment (9080), Service ClusterIP 9080 |
| `reviews` | 3 Deployments `reviews-v1/v2/v3`, mesma imagem `app`, env `SERVICE_VERSION`, `ENABLE_RATINGS` (`false`/`true`/`true`), `STAR_COLOR` (`black`/`black`/`red`), `RATINGS_HOSTNAME=ratings.ratings`; Service ClusterIP 9080 seletor comum `app.kubernetes.io/name: reviews` |
| `ratings` | Deployment (9080), Service ClusterIP 9080 |

Todos: label `backstage.io/kubernetes-id: <app>` no Deployment, Pod template e Service; probes HTTP em `/health` (os quatro serviços expõem esse caminho na tag `1.31.1`); `resources.requests` pequenos e `limits.memory` (Liberty: 512Mi). Namespace = nome da app (regra do ApplicationSet), por isso os hostnames com namespace.

### `scripts/foundry/seed-bookinfo` (novo)

Bash, opções longas (`--istio-tag`, default `1.31.1`; `--dry-run` não cria nada no GitHub). Idempotente: repo existente é pulado com aviso.

1. Sparse checkout de `istio/istio@<tag>` (`samples/bookinfo/src`) num diretório temporário.
2. Para cada `svc` em `productpage details reviews ratings`: copia `src/<svc>/` como raiz do repo; acrescenta de `scripts/foundry/assets/bookinfo/<svc>/` o `catalog-info.yaml` e (backends) o `openapi.yaml`; acrescenta `scripts/foundry/assets/bookinfo/ci.yaml` como `.github/workflows/ci.yaml` e o `LICENSE` Apache-2.0 do Istio; commit; `gh repo create wasp-foundry/<svc> --public` + push; proteção da `main` igual à do template (PR obrigatório, `required_approving_review_count: 0`).
3. Um PR em `wasp-foundry/gitops` com `apps/<svc>/` para os quatro, a partir de `scripts/foundry/assets/bookinfo/gitops/<svc>/`, com a tag de cada overlay = SHA do commit inicial do repo correspondente.

### CI dos repos Bookinfo (`scripts/foundry/assets/bookinfo/ci.yaml`)

Igual ao `ci.yaml` do template `python-service` sem o job `test` (os testes do `productpage` rodam dentro do `docker build` upstream; os outros três não têm testes upstream), com o `bump` apontando para `apps/<app>/overlays/development`. Em `pull_request` o `build` roda sem push, para o `docker build` (e os testes do `productpage` dentro dele) falhar antes do merge.

### Template `python-service` (migração)

- `gitops/` vira `gitops/base/{deployment,service,kustomization}.yaml` + `gitops/overlays/{development,production}/kustomization.yaml`; o PR de criação grava a tag do primeiro commit nos dois overlays.
- `content/.github/workflows/ci.yaml`: o `bump` passa a operar em `apps/<app>/overlays/development`.
- `test-render` renderiza base + overlays e valida os dois `kustomize build`; `test-dry-run` ganha o caso "os dois overlays recebem a tag".
- `content/catalog-info.yaml` ganha `dependsOn` nos Resources `development` e `production`.

### `hello-alpha` (migração)

Um commit direto no `gitops` converte `apps/hello-alpha/` para base + overlays com a tag atual nos dois; um PR no repo `hello-alpha` ajusta o `ci.yaml` (bump em `overlays/development`) e o `catalog-info.yaml` (`dependsOn`).

### Backstage (`idp/`)

- `@backstage/plugin-catalog-backend-module-github` adicionado ao backend; `catalog.providers.github.wasp-foundry`: `organization: wasp-foundry`, `catalogPath: /catalog-info.yaml`, `filters.branch: main`, `schedule` a cada 5 min. Autentica pelo App `wasp-foundry-backstage` (integração existente; Contents R e Metadata R bastam).
- `catalog.rules` global (`[Component, System, API, Resource, Location]`) não muda; a location de `idp/catalog/bookinfo.yaml` declara a própria regra `allow: [Domain, System, Resource]`, porque `Domain` não está no global. O provider github só ingere `Component` e `API`, cobertos pelo global.
- `kubernetes.clusterLocatorMethods[0].clusters`: `development` (`https://127.0.0.1:6551`, `K8S_DEVELOPMENT_TOKEN/CA`) e `production` (`https://127.0.0.1:6552`, `K8S_PRODUCTION_TOKEN/CA`); o `cluster-zero` sai.

## Tratamento de erros

- `seed-bookinfo` com `set -e`: falha no meio deixa repos já criados; rodar de novo pula os existentes e segue. O PR do `gitops` só é aberto depois dos quatro repos.
- Primeiro build: o PR do `gitops` fixa a tag do commit inicial; se mergeado antes do CI publicar a imagem, o pod fica em `ImagePullBackOff` até a imagem existir (mesmo comportamento da #101).
- `promote.yaml` recusa app inexistente e promoção sem mudança, sem abrir PR.
- Cluster de destino fora do ar: a Application correspondente fica `Unknown`; a outra segue — os ambientes não dependem um do outro.

## Riscos a validar primeiro

1. **ArgoCD alcança a API dos clusters de destino pela rede `k3d-idp`** com o certificado do k3s (SAN inclui `k3d-<nome>-server-0`?). Validar com um cluster descartável antes de reescrever `cluster-create`. Fallback: `insecure: true` no Secret de cluster (registrar em known-broken).
2. **Build do `reviews` no runner do GitHub** (gradle + Liberty, multi-stage) cabe no tempo e na memória do `ubuntu-24.04`. Validar no primeiro push do seed.
3. **Memória da máquina** com 5 nós k3d + 3 JVMs Liberty × 2 clusters. Medir com `docker stats` na aceitação; se apertar, `production` roda só `reviews-v1` (overlay remove v2/v3).

## Limitações aceitas (registrar em `aws/docs/known-broken.md`)

- `argocd-manager` com `cluster-admin` nos clusters de destino (padrão do `argocd cluster add`).
- Promoção não verifica que a imagem rodou bem em development — qualquer tag de development pode ser promovida.
- Uma porta de host por cluster, reservada ao `productpage`; `hello-alpha` e apps do template continuam por `port-forward`.

## ADRs a escrever na implementação

- `0019` — clusters de ambiente gerenciados pelo ArgoCD central do cluster-zero (matrix generator, base + overlays, promoção por PR).
- `0020` — descoberta do catalog pela org `wasp-foundry` em vez de registro por repo.

## Testes

- **Offline:** `test-render` (base + dois overlays, `kustomize build` dos dois, server-side dry-run quando houver cluster); `test-dry-run` com o caso novo; `actionlint` em `ci.yaml` (template e Bookinfo) e `promote.yaml`; `shellcheck` em todo script novo ou alterado; `seed-bookinfo --dry-run` monta os quatro repos localmente e roda `docker build` de cada um.
- **Aceitação ponta a ponta:**
  1. Backstage: Domain `bookstore` → System `bookinfo` → 4 Components, 3 APIs com aba Definition renderizada; grafo de relações mostra provides/consumes e `dependsOn` dos Resources.
  2. Aba Kubernetes de cada Component: pods em `development` e em `production`.
  3. `curl http://localhost:9081/productpage` e `:9082/productpage`: página com detalhes do livro e reviews; com refresh, estrelas pretas (v2) e vermelhas (v3) aparecem — prova a chamada entre namespaces.
  4. Mudança por PR em `details` chega só a development; `promote.yaml` abre o PR; merge leva a production.
  5. `hello-alpha` convertida roda nos dois clusters; uma app nova pelo template nasce nos dois.
  6. Restart do backend: o catalog se reconstrói pela descoberta da org (Bookinfo e `hello-alpha` voltam sem registro manual).

## Fora de escopo

Istio instalado nos clusters; ingress; Users além de `guest`; TechDocs; `helloworld`/`httpbin`; tela de "o que está promovido"; isolamento por `AppProject` (já registrado em known-broken item 26).
