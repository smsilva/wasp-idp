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

## Scripts

One-time setup utilities in `scripts/` (not part of daily workflow):

| Script | Purpose |
|--------|---------|
| `scripts/install.sh` | Installs nvm, Node v24, Yarn, creates the Backstage app |
| `scripts/configure.sh` | Installs PostgreSQL 18 and configures the production DB |
| `scripts/cluster-zero/up` | Stands up a local k3d cluster (3 servers) with ArgoCD + Crossplane (Azure providers) — disposable exercise for the "cluster zero" bootstrap described in `docs/superpowers/specs/2026-08-07-multi-tenant-idp-design.md` |
| `scripts/cluster-zero/verify` | Checks health of the cluster, ArgoCD, and Crossplane |
| `scripts/cluster-zero/cluster-delete` | Tears down the cluster |

## Architecture decisions (recorded)

- **Ingress é único, pelo hub (decidido 2026-08-26):** nenhuma spoke expõe acesso a si direto na internet. Vale para qualquer entrada, HTTPS ou VPN — logo um VGW numa spoke também está fora.
- **VPN de cliente termina no hub, uma `Site-to-Site VPN` por cliente (decidido 2026-08-26):** um attachment por cliente no TGW ⟹ a route table de tenant no TGW isola nas **duas** direções, sem depender de security group para separar cliente de cliente.
- **Fronteira de state segue o ciclo de vida, não a conta (decidido 2026-08-26):** recurso da conta do hub cujo ciclo de vida é o de um spoke (route table de tenant, target group, listener rule, certificado do cluster) mora no state do spoke, via provider aliasado. Destruir a célula leva tudo junto, sem órfão do lado do hub.
- **Ingress: ALB no hub → NLB interno na spoke → gateway Istio (decidido 2026-08-26):** o NLB é do Terraform e o `istio-ingressgateway` vira `ClusterIP` com `TargetGroupBinding` — cardinalidade 1 por cluster, e se o LBC criasse o NLB o ARN só existiria depois do workload, quebrando o apply único. Nada cruza conta em tempo de execução.
- **Sequência de provisionamento — dois pares de specs, um só autoritativo (2026-08-27):** `docs/superpowers/specs/2026-08-27-provisioning-sequence.md` + `-resource-dictionary.md` (61 recursos, um arquivo cada) descrevem a sequência **deste** repo, de `00 · accounts` a `08 · provas de isolamento`. O par `2026-08-20-*` é retrato histórico do monólito Crossplane da trilha corporativa — consultar como referência, não como estado. Ao acrescentar camada ou recurso, atualizar os três: sequência, índice e arquivo do recurso.

- **Apps criadas pelo Backstage vivem na org `wasp-foundry`, não em `smsilva` (decidido 2026-09-30):** o `wasp-idp` fica em `smsilva/wasp-idp` — transferi-lo muda owner e owner id e quebra a trust OIDC da role de CI (`aws/terraform/ci/main.tf`, `repo:${github_org}@${github_owner_id}/...`). Desenho em `docs/superpowers/specs/2026-09-30-foundry-app-scaffolding-design.md`.

## Software Templates — gotchas

- Liste `.github/workflows/*` em `copyWithoutTemplating` no `fetch:template`: o Actions usa a mesma sintaxe `${{ }}` do scaffolder, e o template quebraria ou renderizaria `${{ github.* }}`. Workflow gerado não recebe `values.*` — derive nomes de `github.event.repository.name`.
- `yarn backstage-cli create-github-app <org>` cria o App só com leitura; permissões de escrita (inclusive **Workflows**, necessária para enviar `.github/workflows/`) são ajustadas à mão nas settings do App.

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
