# Foundry App Scaffolding — Design

Issue [#101](https://github.com/smsilva/wasp-idp/issues/101). Depende de [#100](https://github.com/smsilva/wasp-idp/issues/100) (upgrade do Backstage 1.49.0 → 1.55.3), que é a etapa 0 deste trabalho.

## Contexto

O app Backstage em `idp/` é o scaffold padrão do `@backstage/create-app` (novo frontend system) mais o módulo de login Google (`idp/packages/backend/src/googleAuthModule.ts`). Os plugins necessários já estão instalados: catalog, scaffolder com `@backstage/plugin-scaffolder-backend-module-github`, org e kubernetes (frontend e backend). O que falta é configuração e conteúdo:

- `integrations.github` usa um PAT (`${GITHUB_TOKEN}`); não há GitHub App.
- O bloco `kubernetes:` de `idp/app-config.yaml` está vazio — o plugin não enxerga nenhum cluster.
- `idp/examples/org.yaml` só tem `user:guest` e o grupo `guests`; o template de exemplo (`idp/examples/template/template.yaml`) grava `owner: user:guest` fixo e usa `RepoUrlPicker` livre.

O Backstage não faz deploy — o plugin kubernetes só lê o estado do cluster. O deploy vem de CI + GitOps.

A org GitHub `wasp-foundry` (plano Free, owner `smsilva`) foi criada para receber o que o Backstage gera. O `wasp-idp` continua em `smsilva/wasp-idp` — transferi-lo quebraria a trust OIDC da role de CI (`aws/terraform/ci/main.tf:44`, que casa `repo:${github_org}@${github_owner_id}/...`).

## Objetivo

Um time cria uma aplicação pelo Backstage e a vê rodando num cluster, de ponta a ponta, num corte fino (walking skeleton).

## Decisões

| Tema | Decisão | Alternativa descartada |
|---|---|---|
| Cluster alvo | k3d do cluster-zero (`scripts/cluster-zero/`), API em `127.0.0.1:6550` | Célula EKS: custo, API privada (exige Client VPN), ingress pelo hub |
| Onde vivem os manifestos | Repositório central `wasp-foundry/gitops`, `apps/<app>/` | Pasta `deploy/` no repo da aplicação + SCM Provider generator; `smsilva/wasp-gitops` (mistura infra de célula com aplicação) |
| Como o template grava no gitops | PR (`publish:github:pull-request`), merge manual | Commit direto: não há action nativa para repo existente, e deixaria o Backstage escrever sem revisão no repo que manda no cluster |
| Como a tag nova chega ao gitops | CI da aplicação faz commit direto (`kustomize edit set image`) com token de GitHub App | ArgoCD Image Updater (componente extra); tag mutável `:main` (Git deixa de dizer o que roda) |
| Visibilidade | Tudo público: repos das aplicações, `gitops`, pacotes GHCR | Privado: exige credencial de repo no ArgoCD (modelo ADR-0012) e pull secret no k3d |
| Times | `Group` estáticos em YAML (`team-alpha`, `team-beta`) | GitHub Teams + `catalog-backend-module-github-org`: o login Google não casa com usuário GitHub |
| Stack do template | Python + FastAPI | Go, Node.js |
| Credenciais GitHub | Dois Apps: `wasp-foundry-backstage` e `wasp-foundry-ci` | Um App só: a chave em secret da org daria a qualquer workflow as permissões do Backstage em todos os repos |
| Onde vive o template | `idp/templates/python-service/` neste repo, location `file` | Repo de templates na org — depois, se houver mais de um template |

## Arquitetura

```
Backstage (yarn start, local)
  │  template "python-service" (OwnerPicker → Group estático)
  ├─① publish:github ──────────► wasp-foundry/<app>        (público)
  │                                 ├─ app/ (FastAPI), Dockerfile
  │                                 ├─ catalog-info.yaml (owner: group:<time>)
  │                                 └─ .github/workflows/ci.yaml
  ├─② publish:github:pull-request ► wasp-foundry/gitops     (público)
  │                                 └─ apps/<app>/ (Deployment, Service, kustomization.yaml)
  └─③ catalog:register ◄──────── catalog-info.yaml do repo novo

wasp-foundry/<app> push na main
  └─ CI: build → ghcr.io/wasp-foundry/<app>:<sha>
       └─ token do App wasp-foundry-ci → kustomize edit set image → commit na main do gitops

k3d (cluster-zero)
  └─ ApplicationSet (Git directory generator em apps/*)
       └─ Application <app> → namespace <app>
  ◄── Backstage lê pods via plugin kubernetes (ServiceAccount read-only)
```

**Primeira imagem:** o PR de criação já grava `apps/<app>/kustomization.yaml` com a tag do primeiro commit do repo da aplicação. Se o PR for mergeado antes de o CI terminar, o pod fica em `ImagePullBackOff` até a imagem existir e se resolve sozinho.

## Componentes

### `idp/` (Backstage)

| Arquivo | Mudança |
|---|---|
| `idp/app-config.yaml` | `integrations.github[0]`: `apps: [ $include: github-app-wasp-foundry-credentials.yaml ]` no lugar de `token: ${GITHUB_TOKEN}` |
| `idp/app-config.yaml` | `kubernetes.serviceLocatorMethod: { type: multiTenant }` e `clusterLocatorMethods: [{ type: config, clusters: [{ name: cluster-zero, url: https://127.0.0.1:6550, authProvider: serviceAccount, serviceAccountToken: ${K8S_CLUSTER_ZERO_TOKEN}, caData: ${K8S_CLUSTER_ZERO_CA} }] }]` |
| `idp/app-config.yaml` | `catalog.locations` ganha `../../catalog/org.yaml` (rules `User`, `Group`) e `../../templates/python-service/template.yaml` (rules `Template`) |
| `idp/catalog/org.yaml` | `Group` `team-alpha` e `team-beta` (`spec.type: team`, `children: []`) |
| `idp/.gitignore` | Sem mudança: já ignora `*-credentials.yaml` (linha 47) |

Backend e frontend não mudam: `publish:github:pull-request` já vem no módulo GitHub instalado, e a aba Kubernetes aparece na entidade que tem a anotação `backstage.io/kubernetes-id`.

### Template `idp/templates/python-service/`

**Parâmetros:**

- `name` — obrigatório, `pattern: '^[a-z]([-a-z0-9]{0,38}[a-z0-9])?$'` (DNS-1123; vira nome de repo, namespace e imagem).
- `description` — obrigatório.
- `owner` — `ui:field: OwnerPicker`, `catalogFilter: { kind: Group }`.
- Sem `RepoUrlPicker`: owner fixo `wasp-foundry`.

**Passos:**

1. `fetch:template` de `./content` → raiz do workspace.
2. `publish:github` — `repoUrl: github.com?owner=wasp-foundry&repo=${{ parameters.name }}`, `repoVisibility: public`, `defaultBranch: main`, `description`.
3. `fetch:template` de `./gitops` → `targetPath: ./gitops-pr/apps/${{ parameters.name }}`, com `imageTag: ${{ steps.publish.output.commitHash }}`.
4. `publish:github:pull-request` — `repoUrl: github.com?owner=wasp-foundry&repo=gitops`, `sourcePath: ./gitops-pr`, `branchName: add-${{ parameters.name }}`, `title: "apps: add ${{ parameters.name }}"`.
5. `catalog:register` — `repoContentsUrl` de `steps.publish`, `catalogInfoPath: /catalog-info.yaml`.

**Output:** links para o repo, o PR do gitops e a entidade no catalog.

**`content/`:**

- `app/main.py` — FastAPI com `GET /` (JSON com nome da aplicação) e `GET /healthz` (`{"status": "ok"}`).
- `requirements.txt` — `fastapi` e `uvicorn` com versão fixada.
- `Dockerfile` — `python:3.13-slim`, usuário não-root, `EXPOSE 8000`, `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]`. Label `org.opencontainers.image.source` apontando para o repo.
- `catalog-info.yaml` — `kind: Component`, `spec.type: service`, `spec.lifecycle: experimental`, `spec.owner: ${{ values.owner }}`, anotações `github.com/project-slug: wasp-foundry/${{ values.name }}` e `backstage.io/kubernetes-id: ${{ values.name }}`.
- `.github/workflows/ci.yaml` — descrito abaixo. Listado em `copyWithoutTemplating`: as expressões `${{ github.* }}` do Actions usam a mesma sintaxe do `fetch:template` e seriam renderizadas (ou quebrariam) pelo scaffolder. Por isso o workflow não recebe valores do template — obtém o nome do repo de `github.event.repository.name`.

**`gitops/`** (vira `apps/<name>/` no repo `gitops`):

- `deployment.yaml` — 1 réplica, label `backstage.io/kubernetes-id: <name>` no Deployment e no template do Pod, probes `readiness`/`liveness` em `/healthz:8000`, `resources` pequenos.
- `service.yaml` — `ClusterIP`, porta 80 → 8000, mesma label.
- `kustomization.yaml` — `resources` dos dois arquivos, `images: [{ name: app, newName: ghcr.io/wasp-foundry/<name>, newTag: <imageTag> }]`.

### CI da aplicação (`.github/workflows/ci.yaml`)

Gatilho: `push` na `main`. Dois jobs:

1. `build` — `permissions: { contents: read, packages: write }`; login no GHCR com `GITHUB_TOKEN`; build e push de `ghcr.io/wasp-foundry/<name>:${{ github.sha }}`.
2. `bump` (`needs: build`) — `actions/create-github-app-token` com `app-id: ${{ vars.FOUNDRY_CI_APP_ID }}`, `private-key: ${{ secrets.FOUNDRY_CI_APP_PRIVATE_KEY }}`, `owner: wasp-foundry`, `repositories: gitops`; checkout do `gitops` com esse token; `kustomize edit set image app=ghcr.io/wasp-foundry/<name>:${{ github.sha }}` em `apps/<name>/`; commit `apps(<name>): deploy <sha curto>`; push com até 3 tentativas de `git pull --rebase` + push.

### `wasp-foundry/gitops`

Criado uma vez (`gh repo create wasp-foundry/gitops --public`) com `README.md` e `apps/.gitkeep`. Sem proteção de branch neste corte: o PR de criação é convenção de revisão, não regra imposta.

### `scripts/cluster-zero/`

- `install-foundry-appset` — aplica `assets/foundry-appset.yaml`.
- `assets/foundry-appset.yaml` — `ApplicationSet` `foundry-apps` em `argocd`: gerador `git` com `repoURL: https://github.com/wasp-foundry/gitops.git`, `revision: main`, `directories: [{ path: apps/* }]`; template com `metadata.name: '{{path.basename}}'`, finalizer `resources-finalizer.argocd.argoproj.io`, `destination.namespace: '{{path.basename}}'`, `syncPolicy.automated: { prune: true, selfHeal: true }`, `syncOptions: [CreateNamespace=true]`, `project: default`.
- `backstage-reader` — cria ServiceAccount `backstage-reader` em `kube-system`, `ClusterRoleBinding` para a `ClusterRole` `view`, `Secret` do tipo `kubernetes.io/service-account-token`, e imprime `export K8S_CLUSTER_ZERO_TOKEN=...` e `export K8S_CLUSTER_ZERO_CA=...`.
- `up` não muda: continua instalando Crossplane. O fluxo de aplicações só precisa de `cluster-create`, `install-argocd`, `install-foundry-appset` e `backstage-reader`.

## Credenciais

| Identidade | Instalado em / escopo | Permissões | Onde fica |
|---|---|---|---|
| App `wasp-foundry-backstage` | Todos os repos da org | Administration RW, Contents RW, Pull requests RW, Workflows RW, Metadata R | `idp/github-app-wasp-foundry-credentials.yaml` (gitignored), gerado por `yarn backstage-cli create-github-app wasp-foundry` |
| App `wasp-foundry-ci` | Só o repo `gitops` | Contents RW, Metadata R | Variável de org `FOUNDRY_CI_APP_ID`, secret de org `FOUNDRY_CI_APP_PRIVATE_KEY` (org secrets funcionam em repos públicos no plano Free) |
| SA `backstage-reader` | cluster-zero | `ClusterRole view` | `K8S_CLUSTER_ZERO_TOKEN`, `K8S_CLUSTER_ZERO_CA` no ambiente do `yarn start` |
| ArgoCD | — | nenhuma credencial | repo `gitops` é público |
| k3d (pull de imagem) | — | nenhuma credencial | pacotes GHCR públicos (ver Riscos) |

`Workflows RW` é obrigatório no App do Backstage: o template envia `.github/workflows/ci.yaml`, e sem essa permissão o GitHub rejeita o push.

## Tratamento de erros

- **Nome já existe:** `publish:github` falha no passo 2, antes de qualquer outra escrita — nada parcial.
- **Falha após o repo criado** (passos 4 ou 5): o scaffolder não faz rollback; sobra repo órfão. Limpeza manual com `gh repo delete wasp-foundry/<name>` e, se houver, fechar o PR `add-<name>` no `gitops`.
- **Corrida no bump:** até 3 tentativas com `pull --rebase`; depois falha visível no Actions.
- **Imagem ainda não publicada:** `ImagePullBackOff` passageiro (ver Arquitetura).
- **Remover uma aplicação:** apagar `apps/<name>/` no `gitops` → o ApplicationSet remove a `Application` → o finalizer apaga os recursos. O namespace criado por `CreateNamespace` fica e é removido à mão. Repo apagado à mão. Sem template de remoção neste corte.

## Riscos a validar primeiro

1. **Visibilidade inicial do pacote GHCR.** Pacote novo numa org pode nascer privado mesmo vindo de repo público, e não há API para mudar a visibilidade. Validar com um repo descartável na `wasp-foundry` antes de escrever o template. Se nascer privado: tornar público pela UI na primeira publicação de cada app não escala — o fallback é um `imagePullSecret` com PAT `read:packages` no namespace, criado pelo ApplicationSet via `ExternalSecret` ou à mão no PoC. — **resultado (2026-09-30):** public, depois de marcar **Public** em "Package creation" (`https://github.com/organizations/wasp-foundry/settings/packages`, sem API — feito pela UI uma vez para a org inteira). Com o default da org o pacote nasceu `private` e o pull anônimo deu `unauthorized`; com Public marcado, pacote novo nasce `public` e o pull anônimo funciona. Nenhum pull secret necessário.
2. **Output `commitHash` do `publish:github`** — resolvido: existe na v1.55.3 (`plugins/scaffolder-backend-module-github/src/actions/github.ts:246`, `ctx.output('commitHash', ...)`). `publish:github:pull-request` aceita `sourcePath` + `targetPath` e devolve `remoteUrl`, `pullRequestNumber`, `targetBranchName`.

## Limitações aceitas (registrar em `aws/docs/known-broken.md`)

- O CI de qualquer repo da org consegue escrever qualquer caminho do `gitops` e portanto fazer deploy de qualquer coisa no k3d. Correção futura: `AppProject` por time com `sourceRepos`/`destinations` restritos e ruleset de path no `gitops`.
- `project: default` no ApplicationSet — sem isolamento entre times no ArgoCD.
- Permissões do Backstage continuam `allow-all` (já catalogado em `docs/idp/CLAUDE.md`).

## ADRs a escrever na implementação

- Repositório GitOps central por org, com criação via PR e bump de tag por commit direto do CI.
- Dois GitHub Apps separados por papel (scaffolding vs. bump de tag).

## Testes

1. **Etapa 0 (#100):** `yarn tsc:full`, `yarn test:all`, smoke manual (login guest e Google, catalog, página Create).
2. **Spike GHCR:** repo descartável publica uma imagem; conferir a visibilidade do pacote e um `docker pull` anônimo. Throwaway — apagar repo e pacote depois.
3. **Template:** dry-run pelo Template Editor (`/create/edit`) — valida parâmetros e renderiza os arquivos sem publicar.
4. **Scripts:** `shellcheck` em `install-foundry-appset` e `backstage-reader`.
5. **Aceitação ponta a ponta** — criar `hello-alpha` (owner `team-alpha`) e conferir, em ordem:
   1. repo público `wasp-foundry/hello-alpha` existe;
   2. entidade no catalog com `owner: group:default/team-alpha`;
   3. PR `add-hello-alpha` aberto no `gitops` → merge;
   4. CI verde e commit de bump no `gitops`;
   5. `Application hello-alpha` Synced/Healthy;
   6. `kubectl --namespace hello-alpha port-forward svc/hello-alpha 8080:80` e `curl localhost:8080/healthz` → 200;
   7. aba Kubernetes da entidade mostra o pod;
   8. push alterando a resposta de `/` chega ao pod com a tag nova.

## Fora de escopo

- Célula EKS como destino (parâmetro `cluster` no template vem depois).
- Mais de um ambiente / promoção entre ambientes.
- GitHub Teams, sincronização de org, login GitHub no Backstage.
- Template de remoção de aplicação.
- Deploy do próprio Backstage no cluster.
