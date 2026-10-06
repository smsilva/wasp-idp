# Backstage IDP

Rules and conventions for the Backstage app. Overview and reading index in
[`README.md`](README.md).

## Branches

The Backstage app lives on `main`. Feature work follows the repo convention: `feat/<issue>-<short-description>` from `main`.

## Commands

All commands must be run from the `idp/` directory. If `yarn` is not on `PATH`, use the vendored release: `node .yarn/releases/yarn-4.4.1.cjs <command>`.

`resolutions` pins `@yarnpkg/core` to `4.9.1`: `4.9.2` was published with `got` pointing to a patch file that only exists in the Yarn monorepo, which breaks `yarn install` (`ENOENT .yarn/patches/got-npm-11.8.2-*.patch`). Drop the pin once a fixed release is out.

```bash
# Development
yarn start          # Start full dev server (frontend :3000 + backend :7007)
yarn new            # Scaffold new packages or plugins

# Build
yarn build:backend  # Build backend only
yarn build:all      # Build all packages
yarn build-image    # Build Docker image for backend

# Test
yarn test           # Run tests (changed files)
yarn test:all       # Run all tests with coverage
yarn test:e2e       # Run Playwright E2E tests

# Lint / Type-check
yarn lint           # Lint changed files since origin/master
yarn lint:all       # Lint everything
yarn tsc            # TypeScript check (incremental)
yarn tsc:full       # Full TypeScript check (no cache)
yarn fix            # Auto-fix lint issues
yarn prettier:check # Check formatting

# Cleanup
yarn clean          # Remove build artifacts
```

## Authentication

SSO via Google OAuth 2.0 alongside Guest.

**Backend module:** `idp/packages/backend/src/googleAuthModule.ts`
- Uses `createBackendModule` + `googleAuthenticator`
- Resolver: `googleSignInResolvers.emailMatchingUserEntityAnnotation` with `dangerouslyAllowSignInWithoutUserInCatalog: true` (PoC — any Google account allowed)

**Config:** `app-config.yaml` reads `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` from env.

**Key pitfalls already solved:**
- Do **not** use `name:` in `SignInPageBlueprint.make` — creates a conflicting second extension
- Do **not** use `@backstage/plugin-auth-backend-module-google-provider` directly — no `signInResolver`, rejects all logins
- Custom backend modules must use `export default` and `backend.add(import('./myModule'))` — async `.then()` races with `backend.start()`

**OAuth callback is handled by the backend (port 7007), not the frontend.**

### Google OAuth setup

1. [console.cloud.google.com](https://console.cloud.google.com) → APIs & Services → Credentials
2. Create OAuth 2.0 Client ID (Web application)
3. Authorized JavaScript origins: `http://localhost:3000`
4. Authorized redirect URIs: `http://localhost:7007/api/auth/google/handler/frame`
5. Export env vars and start:
   ```bash
   export GOOGLE_CLIENT_ID=<id>.apps.googleusercontent.com
   export GOOGLE_CLIENT_SECRET=<secret>
   cd idp && yarn start
   ```

### GitHub integration

The backend authenticates to GitHub as the App `wasp-foundry-backstage` (org `wasp-foundry`, App ID `5142977`, Client ID `Iv23liH08qVKNLmjORO7`), not a PAT. `idp/app-config.yaml` includes `idp/github-app-wasp-foundry-backstage-credentials.yaml`, which is gitignored, lives only on each machine (not in Secrets Manager) and must exist before `yarn start`.

**New machine:** the App already exists — do not run `create-github-app` again. In `https://github.com/organizations/wasp-foundry/settings/apps/wasp-foundry-backstage`, click **Generate a new client secret** and **Generate a private key** (GitHub never re-downloads an existing key; each machine gets its own, and the others stay valid). Write the file with mode `600` and delete the downloaded `.pem`:

```yaml
appId: 5142977
clientId: Iv23liH08qVKNLmjORO7
clientSecret: <client secret>
privateKey: |
  -----BEGIN RSA PRIVATE KEY-----
  ...
```

To recreate the App from scratch: `yarn backstage-cli create-github-app wasp-foundry`, then raise the permissions to Administration/Contents/Pull requests/Workflows RW in the App settings (the CLI creates it read-only). The CI App `wasp-foundry-ci` is not needed by Backstage — its key is the org secret `FOUNDRY_CI_APP_PRIVATE_KEY` ([ADR 0018](../adr/0018-separate-github-apps-per-role.md)).

## Scripts

One-time setup utilities in `scripts/` (not part of daily workflow):

| Script | Purpose |
|--------|---------|
| `scripts/install.sh` | Installs nvm, Node v24, Yarn, creates the Backstage app |
| `scripts/configure.sh` | Installs PostgreSQL 18 and configures the production DB |
| `scripts/cluster-zero/check-prereqs` | Checks the CLI tools and `fs.inotify.max_user_instances` ≥ 1024 (the default 128 keeps containerd from starting with five k3d nodes) |
| `scripts/cluster-zero/up` | Stands up three local k3d clusters on the `k3d-idp` network — `idp-cluster-zero` (3 servers, ArgoCD + Crossplane + the `foundry-apps` ApplicationSet), `development` and `production` (1 server each, registered as ArgoCD destinations) — disposable exercise for the "cluster zero" bootstrap described in `docs/superpowers/specs/2026-08-07-multi-tenant-idp-design.md` |
| `scripts/cluster-zero/verify` | Checks health of the cluster, ArgoCD, and Crossplane |
| `scripts/cluster-zero/install-foundry-appset` | Applies the `foundry-apps` ApplicationSet: a matrix of the `development`/`production` clusters × the `apps/*` directories of `wasp-foundry/gitops`, one `<app>-<env>` ArgoCD `Application` each (`apps/<app>/overlays/<env>`) |
| `scripts/cluster-zero/backstage-reader` | Creates a read-only ServiceAccount in one cluster and prints `K8S_<NAME>_TOKEN`/`K8S_<NAME>_CA` for the Backstage kubernetes plugin — `eval "$(scripts/cluster-zero/backstage-reader --cluster development)"` (and `production`) before `yarn start` |
| `scripts/cluster-zero/cluster-create` | Creates one k3d cluster: `--name`, `--api-port` (required), `--servers`, `--network` (default `k3d-idp`), `--app-port` |
| `scripts/cluster-zero/register-clusters` | Registers `development` and `production` as ArgoCD destinations in `idp-cluster-zero` (ServiceAccount `argocd-manager` + cluster Secret with label `env`) — idempotent |
| `scripts/foundry/seed-bookinfo` | Imports the Istio Bookinfo services into `wasp-foundry` (one repo per service + one gitops PR) — idempotent; `--dry-run` builds everything locally |
| `scripts/foundry/test-seed-bookinfo` | Tests the seed's recovery paths with a stubbed `gh`: empty/unprotected existing repo, gitops PR already open |
| `scripts/foundry/test-bookinfo-assets` | Validates the seed assets offline: catalog entities, OpenAPI, gitops overlays, CI |
| `scripts/cluster-zero/cluster-delete` | Tears down the clusters; no argument deletes `idp-cluster-zero`, `development` and `production` |
| `scripts/single-cluster/up` | Lightweight alternative to `cluster-zero/up`: one k3d `idp-single` (API `:6553`) with namespaces `development` and `production`, every `apps/*/overlays/<env>` of `wasp-foundry/gitops` applied with `kubectl apply -k` — no ArgoCD, no Crossplane |
| `scripts/single-cluster/backstage-reader` | One read-only ServiceAccount per namespace (`RoleBinding` to `view`) in `idp-single`; prints `K8S_SINGLE_<ENV>_TOKEN`/`_CA` — `eval "$(scripts/single-cluster/backstage-reader)"`, then `yarn start --config "$PWD/app-config.yaml" --config "$PWD/app-config.single-cluster.yaml"` from `idp/` (`repo start` resolves relative `--config` paths against `packages/backend`) |
| `scripts/single-cluster/backstage-start` | One-shot local run: `up` (reuses an existing `idp-single`; `--recreate` runs `down` first), `eval` of `backstage-reader`, then `yarn start` with `app-config.yaml` + `app-config.single-cluster.yaml` as absolute paths — extra `--config <file>` (e.g. `app-config.flow.local.yaml`) appended in order |
| `scripts/single-cluster/down` | Deletes `idp-single` |

**Promotion to production:** each app's CI bumps only `apps/<app>/overlays/development`. To promote: `gh workflow run promote.yaml --repo wasp-foundry/gitops -f app=<app>`, then merge the pull request it opens; the `<app>-production` Application syncs the new tag. The host needs `fs.inotify.max_user_instances` ≥ 1024 (the default 128 keeps containerd from starting with five k3d nodes) and the org setting "Allow GitHub Actions to create and approve pull requests" on.

## Architecture decisions (recorded)

- **Ingress é único, pelo hub (decidido 2026-08-26):** nenhuma spoke expõe acesso a si direto na internet. Vale para qualquer entrada, HTTPS ou VPN — logo um VGW numa spoke também está fora.
- **VPN de cliente termina no hub, uma `Site-to-Site VPN` por cliente (decidido 2026-08-26):** um attachment por cliente no TGW ⟹ a route table de tenant no TGW isola nas **duas** direções, sem depender de security group para separar cliente de cliente.
- **Fronteira de state segue o ciclo de vida, não a conta (decidido 2026-08-26):** recurso da conta do hub cujo ciclo de vida é o de um spoke (route table de tenant, target group, listener rule, certificado do cluster) mora no state do spoke, via provider aliasado. Destruir a célula leva tudo junto, sem órfão do lado do hub.
- **Ingress: ALB no hub → NLB interno na spoke → gateway Istio (decidido 2026-08-26):** o NLB é do Terraform e o `istio-ingressgateway` vira `ClusterIP` com `TargetGroupBinding` — cardinalidade 1 por cluster, e se o LBC criasse o NLB o ARN só existiria depois do workload, quebrando o apply único. Nada cruza conta em tempo de execução.
- **Sequência de provisionamento — dois pares de specs, um só autoritativo (2026-08-27):** `docs/superpowers/specs/2026-08-27-provisioning-sequence.md` + `-resource-dictionary.md` (61 recursos, um arquivo cada) descrevem a sequência **deste** repo, de `00 · accounts` a `08 · provas de isolamento`. O par `2026-08-20-*` é retrato histórico do monólito Crossplane da trilha corporativa — consultar como referência, não como estado. Ao acrescentar camada ou recurso, atualizar os três: sequência, índice e arquivo do recurso.

- **Apps criadas pelo Backstage vivem na org `wasp-foundry`, não em `smsilva` (decidido 2026-09-30):** o `wasp-idp` fica em `smsilva/wasp-idp` — transferi-lo muda owner e owner id e quebra a trust OIDC da role de CI (`aws/terraform/ci/main.tf`, `repo:${github_org}@${github_owner_id}/...`). Desenho em `docs/superpowers/specs/2026-09-30-foundry-app-scaffolding-design.md`.

## Upgrades — gotchas

- Since 1.55 every `page:*` extension becomes a nav item on its own; anything `Sidebar.tsx` renders by hand (search, user-settings, notifications) must be removed with `nav.take('page:<id>')`, otherwise it shows up again in `nav.rest` — `nav-item:*: false` keys in `app-config.yaml` no longer apply.
- After `versions:bump`, a `TS2344` on `DateValue` in `node_modules/@backstage/ui` means two copies of `@internationalized/date`: run `yarn dedupe '@internationalized/*' '@react-aria/*' 'react-aria*' '@react-stately/*' 'react-stately' '@react-types/*'`.

## Software Templates — gotchas

- Liste `.github/workflows/*` em `copyWithoutTemplating` no `fetch:template`: o Actions usa a mesma sintaxe `${{ }}` do scaffolder, e o template quebraria ou renderizaria `${{ github.* }}`. Workflow gerado não recebe `values.*` — derive nomes de `github.event.repository.name`.
- `yarn backstage-cli create-github-app <org>` cria o App só com leitura; permissões de escrita (inclusive **Workflows**, necessária para enviar `.github/workflows/`) são ajustadas à mão nas settings do App.

- Render free-text parameters in YAML with `${{ values.x | dump }}` (JSON string): unquoted interpolation lets a description with newlines inject keys into `catalog-info.yaml`. Validate entity refs with a `pattern` — `OwnerPicker` only constrains the UI, the scaffolder API accepts any string.
- `publish:github` protects the default branch with 1 required approval + `enforce_admins` by default, which freezes repos in a one-member org; set `requiredApprovingReviewCount: 0`.
- Run a template for real without the UI: `POST /api/scaffolder/v2/tasks` with `{"templateRef": "template:default/python-service", "values": {...}}` and the guest token, then poll `GET /api/scaffolder/v2/tasks/<id>` until `status` is `completed`/`failed` (errors are in `/tasks/<id>/events`).
- Test a template without publishing via `POST /api/scaffolder/v2/dry-run` (guest token from `GET /api/auth/guest/refresh`); `idp/templates/python-service/test-dry-run` is the reference.

## Local backend — gotchas

- The local DB is SQLite `:memory:`, but repos of the `wasp-foundry` org come back on their own: the GitHub entity provider (`catalog.providers.github.waspFoundry`) rescans `/catalog-info.yaml` on `main` every 5 min (first run 15 s after start). Only entities registered by hand from elsewhere vanish on restart.
- New `catalog.locations` in `app-config.yaml` are not hot-reloaded — restart `yarn start`.
- Stop `yarn start` before switching branches: the dev server hot-reloads the other branch's files and does not recover cleanly on switching back (stale cards/modules until restart).
- The Kubernetes tab groups by cluster entry, never by namespace, and the backend lists by `backstage.io/kubernetes-id` across all namespaces. To show namespaces as environments, `app-config.single-cluster.yaml` declares the same API server twice with a `namespace` key, which `packages/backend/src/namespaceScopedFetcherModule.ts` turns into a namespaced fetch — without it a ServiceAccount bound to one namespace gets 403 on the cluster-wide list.

## Entity page — conventions

- Keep every entity page on the same layout: stock catalog cards (`has-*`, `depends-on-*`) on the Overview, no kind-specific tabs or custom list cards. Custom Domain cards and a Dependencies tab were built and dropped for breaking homogeneity between kinds.
- Hide empty stock relation cards with a `config.filter` in `app-config.yaml`, not code: `relations: { $contains: { type: hasPart, targetRef: { $hasPrefix: 'system:' } } }` (filter predicates support `$contains`, `$hasPrefix`, `$in`, `$exists`, `$not`).
- Change stock page params (e.g. `noHeader`) with `catalogPlugin.getExtension('page:catalog/entity').override({ params: {...} })` in a frontend module; `app.extensions` config only exposes `path`/`title`.
- The BUI `Header` has no icon slot and its `className` lands on the title row, not a wrapper; `HeaderNav` is not exported. The custom header renders identity above it and hides that row to keep only the tabs.
- `renderTestApp` takes extension definitions (the blueprint `make` results), not `module.extensions`; test cards with `createTestEntityPage` + `catalogApiMock` from `@backstage/plugin-catalog-react/testUtils` (the in-memory client honours `relations.<type>` filters).
- Stack PRs carefully: merging a PR whose base is another feature branch right after that base merges lands it on the feature branch, not `main` (#132). Merge the base first and wait for GitHub to retarget, or open the follow-up against `main`.

## Catalog examples and TechDocs

- `idp/catalog/communication/` is the example of a richer model (#114): Domain `communication` with subdomains `messaging`/`notifications` (`spec.subdomainOf`, shown as `partOf`/`hasPart`), Systems `greeter`/`notifier`, and database/topic/queue/bucket Resources attached to `greeting-api`/`notification-api` with `dependencyOf` — so the Components' repos only carry `spec.system`. The Resources are descriptive; nothing provisions them. Names share one singular subject prefix per System (`greeting-*`, `notification-*`), so a search for the prefix returns the whole System (#116).
- Resources are cloud-agnostic: describe them by role, never by cloud service. `spec.type` is one of `database`, `queue`, `topic`, `object-storage`, `llm-provider`, `speech-to-text`, `kubernetes-cluster` (each has an icon in `packages/app/src/modules/entityPresentation`); descriptions say "relational database", "message queue", "pub/sub topic", "object storage bucket", not PostgreSQL/SQS/SNS/S3; no cloud tags (`sns`, `s3`...).
- TechDocs in both patterns: next to the catalog file in this repo (`backstage.io/techdocs-ref: dir:.` on the Domain, `dir:./greeter` on the System) and in the service repo (`mkdocs.yml` + `docs/` in `wasp-foundry/greeting-api`/`notification-api`). Docs are built on first view with the `spotify/techdocs:v1.2.8` image (`generator.runIn: docker`); check a site offline with `docker run --rm --volume "$PWD":/content --workdir /content spotify/techdocs:v1.2.8 build --strict`. No mermaid addon is installed — use text diagrams.

## Security TODOs (PoC hardening, deferred)

Flagged by automated security review — intentional PoC shortcuts, to revisit before any real deployment:

- `idp/app-config.production.yaml`: `guest` auth provider is enabled in production config — should be dev-only.
- `idp/packages/backend/src/googleAuthModule.ts`: `dangerouslyAllowSignInWithoutUserInCatalog: true` lets any Google account sign in without a catalog `User` entity.
- `idp/packages/backend/src/index.ts`: uses `@backstage/plugin-permission-backend-module-allow-all-policy` — no real authorization policy in place.

## Targets

- Backstage as IDP foundation
- Crossplane integration
- SSO via Google OIDC
- CI/CD via GitHub Actions
- Minimal UI customisation — easy to maintain across Backstage upgrades
