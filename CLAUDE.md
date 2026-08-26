# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

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

- **azurerm version:** `infra/terraform/cluster-zero/` uses `azurerm ~> 4.x` (modern). Do NOT add the new AKS module to `azure-platform-foundation` — that repo is pinned to `azurerm 2.72.0` and would require a risky full upgrade.
- **Cluster-zero Terraform boundary:** Terraform provisions AKS + installs ArgoCD only. Crossplane and Azure providers arrive via GitOps (app-of-apps) after ArgoCD is up — not via Terraform.
- **Platform Library vs. per-project GitOps repo:** central Crossplane Compositions/XRDs live in a read-only Platform Library repo; each project's GitOps config lives in its own write-restricted repo (only that project's Backstage instance can write to it). This is the blast-radius/write-access isolation boundary.
- **Per-project isolation model:** security boundary is a separate Backstage instance per project (separate namespace, separate GitOps repo, separate GitHub org) — not RBAC inside a shared instance. One project's team must not be able to discover another project's existence.
- **Crossplane provider wait timeout:** on a resource-contrained host (8 cores, 3-node k3d), the 10 Azure providers can take >600 s to reach `Healthy` due to apiserver patch pressure under etcd load. Use `--timeout=900s` for `kubectl wait provider --all --for condition=Healthy`.
- **Ingress é único, pelo hub (decidido 2026-08-26):** nenhuma spoke expõe acesso a si direto na
  internet. Vale para qualquer entrada, HTTPS ou VPN — logo um VGW numa spoke também está fora.
- **VPN de cliente termina no hub, uma `Site-to-Site VPN` por cliente (decidido 2026-08-26):** um
  attachment por cliente no TGW ⟹ a route table de tenant no TGW isola nas **duas** direções, sem
  depender de security group para separar cliente de cliente.
- **Cluster naming idea (not decided):** OpenStack's TripleO project uses `Undercloud` (the bootstrap/control cluster that deploys and manages) and `Overcloud` (the workload cluster it produces) — possible naming inspiration for cluster-zero (undercloud-like) vs. per-project Backstage clusters (overcloud-like).

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

## This file

Update as the project evolves. It is the primary reference for Claude when working in this repo.
