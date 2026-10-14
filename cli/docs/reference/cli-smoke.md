# Smoke test

`scripts/demo/cli-smoke` (#179) is the automated test of the CLI: it runs the walkthrough flow end to end against `platform-local` and stops at the first failure, with a non-zero exit code. Run it before merging a CLI change; each new command adds its step to it.

```bash
scripts/demo/cli-smoke              # from scratch, with platform init

# reuses the platform-local that is already up
scripts/demo/cli-smoke \
  --skip-init
```

It signs in with test users instead of the browser, so it needs no one at the keyboard. What depends on a browser or a GitHub org owner stays out: creating and installing the GitHub App, and the happy paths of `component create` and `build create`. Those are covered only by the [walkthrough](../walkthrough/index.md).

Each step opens with `== [<n>/<total> · <elapsed>] <step>`, so a slow `--wait` reads apart from a hung one. A refusal the step expects is printed as `  expected refusal: <message>`, never as a bare `✗`. Redirected to a file (`cli-smoke > smoke.log`), the output has no colors.

!!! note
    The test users `platform-smoke` (`platform-users`) and `platform-smoke-admin` (`platform-admins`) and the client `platform-smoke` exist **only on the local target**. The rationale for the password grant is in `platform/keycloak/README.md`.
