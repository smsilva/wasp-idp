# Backstage IDP PoC

Internal Developer Portal proof-of-concept built on [Backstage](https://backstage.io) v1.49.0.

## Stack

| Component | Version |
|-----------|---------|
| Backstage | 1.49.0 |
| Node.js | 24 |
| Yarn | 4.4.1 |
| Database (dev) | SQLite in-memory |
| Database (prod) | PostgreSQL |

## Quick start

```bash
cd idp
export GOOGLE_CLIENT_ID=<your-client-id>.apps.googleusercontent.com
export GOOGLE_CLIENT_SECRET=<your-secret>
yarn start
```

Frontend: http://localhost:3000 — Backend: http://localhost:7007

## Structure

```
idp/           # Backstage Yarn workspaces monorepo
  packages/
    app/       # React frontend
    backend/   # Node.js backend
  plugins/     # Custom plugins (empty)
  examples/    # Sample catalog entities and templates
scripts/       # One-time environment setup (install, configure PostgreSQL)
```

## UI customisations

- **Theme:** custom blue palette (navy sidebar, `#1565C0` primary) with light and dark variants
- **Navigation:** manually ordered sidebar — Catalog, Scaffolder, then remaining items
- **Logo:** Backstage SVG logo in `#7df3e1`
- **Sign-in:** Guest + Google OAuth 2.0

See `CLAUDE.md` for full technical details and pitfalls.

## Authentication

Google OAuth 2.0 via a custom backend module. The OAuth redirect URI points to the **backend** (port 7007):

```
http://localhost:7007/api/auth/google/handler/frame
```

Set up credentials at [console.cloud.google.com](https://console.cloud.google.com) → APIs & Services → Credentials (Web application type).

## First-time setup

```bash
# Install Node 24, Yarn, create the app
./scripts/install.sh

# Install and configure PostgreSQL 18 (production)
./scripts/configure.sh
```

## Local cluster-zero exercise

A disposable k3d cluster (3 servers) with ArgoCD and Crossplane (Azure providers), used to exercise the "cluster zero" bootstrap from the multi-tenant IDP design before it's reimplemented in Terraform against real Azure AKS.

```bash
scripts/cluster-zero/up      # stand up cluster + ArgoCD + Crossplane
scripts/cluster-zero/verify  # check health of everything
scripts/cluster-zero/cluster-delete  # tear down
```
