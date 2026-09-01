# Backstage IDP

Índice de leitura e visão geral do app Backstage. Comandos de dev/build/test, regras de
autenticação e convenções ficam em [`CLAUDE.md`](CLAUDE.md).

## Project Overview

Backstage Internal Developer Portal (IDP) proof-of-concept. The Backstage app lives in `idp/` as a Yarn 4 workspaces monorepo. Supporting scripts are in `scripts/`.

This `docs/idp/` folder is scoped to the Backstage tool itself. AWS infrastructure documentation (hub-and-spoke reference architecture, ADRs, known-broken, open questions, lessons learned) lives in `aws/docs/` and `docs/adr/`, not here — the two initiatives are separate.

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
