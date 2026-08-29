## Project Overview

Backstage Internal Developer Portal (IDP) proof-of-concept. The Backstage app lives in `idp/` as a Yarn 4 workspaces monorepo. Supporting scripts are in `scripts/`.

## Branches

| Branch | Purpose |
|--------|---------|
| `main` | Stable base — scripts and repo config only |
| `dev`  | Active development — full Backstage app with UI customisations |

Always branch from `dev` for feature work on the IDP.

## Commands

All commands must be run from the `idp/` directory.

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

## Architecture

### Monorepo structure

```
idp/
├── packages/
│   ├── app/        # React frontend — UI shell, plugins, themes, nav
│   └── backend/    # Node.js backend — plugins, DB, auth
├── plugins/        # Custom plugins (currently empty)
└── examples/       # Sample catalog entities and software templates
```

### Configuration files

| File | Used when |
|------|-----------|
| `idp/app-config.yaml` | Local development (SQLite in-memory) |
| `idp/app-config.production.yaml` | Production (PostgreSQL via env vars) |

Production DB env vars: `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`.

### Backstage version

**v1.49.0** (`idp/backstage.json`). Toolchain: `@backstage/cli` 0.36.0, Yarn 4.4.1, Node.js 24.

## UI Customisations

All customisations follow Backstage's declarative frontend system — no patches to core packages.

### Theme — `idp/packages/app/src/themes/blueTheme.ts`

Two custom themes (blue-light / blue-dark) built with `createUnifiedTheme` + `ThemeBlueprint.make`:

- Sidebar: navy `#0A1929` (light), deep navy `#071423` (dark)
- Primary: `#1565C0` (light), `#42A5F5` (dark)
- Default themes (`theme:app/light`, `theme:app/dark`) are **disabled** in `app-config.yaml`

### Navigation — `idp/packages/app/src/modules/nav/`

| File | What it does |
|------|-------------|
| `Sidebar.tsx` | Custom sidebar via `NavContentBlueprint.make`; manually orders Catalog, Scaffolder, then rest |
| `SidebarLogo.tsx` | Mounts `LogoFull` / `LogoIcon` in the sidebar header |
| `LogoFull.tsx` | Full Backstage SVG logo, coloured `#7df3e1` |
| `LogoIcon.tsx` | Icon-only version of the logo |

Nav items `search`, `user-settings`, `catalog`, and `scaffolder` are disabled via `app-config.yaml` extensions and re-added manually in `Sidebar.tsx` to control order.

### Sign-in page — `idp/packages/app/src/modules/auth/SignInPage.tsx`

Overrides the default `sign-in-page:app` extension via `SignInPageBlueprint.make` (no `name:` param — omitting it replaces the singleton default). Offers Guest and Google OAuth providers.

### App entry point — `idp/packages/app/src/App.tsx`

```ts
createApp({ features: [catalogPlugin, navModule, blueThemeModule, authModule] })
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

## Architecture decisions (recorded)

- **Ingress é único, pelo hub (decidido 2026-08-26):** nenhuma spoke expõe acesso a si direto na internet. Vale para qualquer entrada, HTTPS ou VPN — logo um VGW numa spoke também está fora.
- **VPN de cliente termina no hub, uma `Site-to-Site VPN` por cliente (decidido 2026-08-26):** um attachment por cliente no TGW ⟹ a route table de tenant no TGW isola nas **duas** direções, sem depender de security group para separar cliente de cliente.
- **Fronteira de state segue o ciclo de vida, não a conta (decidido 2026-08-26):** recurso da conta do hub cujo ciclo de vida é o de um spoke (route table de tenant, target group, listener rule, certificado do cluster) mora no state do spoke, via provider aliasado. Destruir a célula leva tudo junto, sem órfão do lado do hub.
- **Ingress: ALB no hub → NLB interno na spoke → gateway Istio (decidido 2026-08-26):** o NLB é do Terraform e o `istio-ingressgateway` vira `ClusterIP` com `TargetGroupBinding` — cardinalidade 1 por cluster, e se o LBC criasse o NLB o ARN só existiria depois do workload, quebrando o apply único. Nada cruza conta em tempo de execução.
- **Sequência de provisionamento — dois pares de specs, um só autoritativo (2026-08-27):** `docs/superpowers/specs/2026-08-27-provisioning-sequence.md` + `-resource-dictionary.md` (61 recursos, um arquivo cada) descrevem a sequência **deste** repo, de `00 · accounts` a `08 · provas de isolamento`. O par `2026-08-20-*` é retrato histórico do monólito Crossplane da trilha corporativa — consultar como referência, não como estado. Ao acrescentar camada ou recurso, atualizar os três: sequência, índice e arquivo do recurso.

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
