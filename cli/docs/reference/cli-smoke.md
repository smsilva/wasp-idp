# Smoke and e2e tests

Two scripts test the CLI against `platform-local` (#179, #451). Both stop at the first failure, with a non-zero exit code.

| Script | Covers | Time on a running `platform-local` | Run it |
|---|---|---|---|
| `scripts/test/cli-smoke` | the control plane: login, status, MCP, catalog and import, teams, templates, SCM, component and build refusals, registries, `workload spec`, cloud accounts | under 2 min | on every CLI change |
| `scripts/test/cli-e2e` | the journey through one vcluster: environment with the mesh, sharing with a team, workloads, instances, routes, `apply`, the Forager, public routes, signals | ~10 min | when a change touches environments, workloads, providers or the mesh, and before a walkthrough run |

A new command adds its step to `cli-smoke` if it needs only the control plane, else to `cli-e2e`.

```bash
scripts/test/cli-smoke              # from scratch, with platform init

# reuses the platform-local that is already up
scripts/test/cli-smoke \
  --skip-init

scripts/test/cli-e2e \
  --skip-init
```

They sign in with test users instead of the browser, so they need no one at the keyboard. What depends on a browser or a GitHub org owner stays out: creating and installing the GitHub App, and the happy paths of `component create` and `build create`. Those are covered only by the [walkthrough](../walkthrough/index.md).

Each step opens with `== [<n>/<total> · <elapsed>] <step>`, so a slow `--wait` reads apart from a hung one. A refusal the step expects is printed as `  expected refusal: <message>`, never as a bare `✗`. Redirected to a file (`cli-smoke > smoke.log`), the output has no colors. The helpers and the `--skip-init` option live in `scripts/test/lib`, which both scripts source.

!!! note
    The test users `platform-smoke` (`platform-users`) and `platform-smoke-admin` (`platform-admins`) and the client `platform-smoke` exist **only on the local target**. The rationale for the password grant is in `platform/keycloak/README.md`.
