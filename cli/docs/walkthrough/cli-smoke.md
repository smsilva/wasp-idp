# Without a browser

The walkthrough has **one human step, the sign-in**. `scripts/demo/cli-smoke` (#179) runs the flow **unattended**: `init`, sign-in with the test user (`platform-users`), the `403` refusal when creating a domain, an environment created with `--wait` and deleted, sign-in with the test admin, `catalog import idp/catalog/` (applied, then `nothing to do`), the templates (`list` as a regular user, `403` refusal on `create`, `render` of the seed with no `${{` left over, the import plan of the Backstage template with the `steps` ignored), the connections (`403` refusal for a regular user; as admin, `add --no-browser` returns the manifest flow URL and the start page takes the manifest to the org, a forged `state` is refused, and `remove`), the refusals of `component create` before anything reaches GitHub (unknown system `422`, a `--param` outside the schema `422`, a name already in the index `409`, a connection in `AppNotCreated` `409`), a cloud account (`409` asking for `--aws-profile` without a base credential; with one, a role the platform does not assume ends up `TrustNotEstablished`, and another user neither sees it nor registers the same role) and `logout`. The smoke does not create an App: the manifest flow needs a browser and an org owner, so creating, installing and reaching `ready` stays in the manual walkthrough of the [GitHub connection](scm-connection/18-1-create-app.md), and so does the happy path of [component create](components/19-1-create.md). It stops at the first failure, with a non-zero exit code.

```bash
scripts/demo/cli-smoke              # from scratch, with platform init

# reuses the platform-local that is already up
scripts/demo/cli-smoke \
  --skip-init
```

!!! note
    The users `platform-smoke` and `platform-smoke-admin` and the client `platform-smoke` exist **only on the local target**. The rationale for the password grant is in `platform/keycloak/README.md`.
