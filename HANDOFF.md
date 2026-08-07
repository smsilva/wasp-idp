# HANDOFF

## Why

Bootstrap the Backstage IDP PoC repository with proper git hygiene and documentation.
`idp/` existed only as `node_modules/` on disk (no source files on the working tree); the actual source code lives in branch `dev`.
Chose to document in `CLAUDE.md` + `README.md` at repo root and add a `.gitignore` rather than touching any source code.

## In Progress

Last step: pushed `main` and `dev` to `origin`.
Intended next: no active work item; repo is clean.

## Open Questions / Hypotheses

- None carried from a previous handoff.
- Whether to surface the three PoC security risks as Jira tasks or GitHub issues (not decided).

## Known Broken

1. `app-config.production.yaml` — `guest: {}` present in production config — **intentional** (PoC only; must be removed before real production use).
2. `packages/backend/src/index.ts` — `allow-all` permission policy — **intentional** (PoC; replace with real `PermissionPolicy` before production).
3. `packages/backend/src/googleAuthModule.ts` — `dangerouslyAllowSignInWithoutUserInCatalog: true` — **intentional** (PoC; restrict by domain or catalog before production).

## How to Resume

```bash
cd /home/silvios/git/backstage
git checkout dev
cd idp && yarn start
```

## Next Steps

- [ ] Restrict `idp/app-config.production.yaml`: remove `guest` provider, keep only Google.
- [ ] Replace `allow-all` permission policy with a real `PermissionPolicy` implementation.
- [ ] Restrict `googleAuthModule.ts` sign-in resolver to a trusted domain or catalog-only.
- [ ] Add Crossplane integration (declared target, not started).
- [ ] Add GitHub Actions CI/CD pipeline (declared target, not started).

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.