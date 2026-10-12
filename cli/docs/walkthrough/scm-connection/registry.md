# Register the registry of the org

A build pushes its image to an **OCI registry** of the platform (ADR 0037). The repos of `wasp-foundry` build on GitHub Actions, whose `GITHUB_TOKEN` writes to the GHCR of the org that owns the repo, so the registry of these builds is `ghcr.io/wasp-foundry`. The connection already knows the org: `verify` suggested the command.

```bash
platform registry add ghcr-wasp-foundry \
  --scm-connection wasp-foundry \
  --default

platform registry list
```

``` { .text .output title="output" }
✓ registry ghcr-wasp-foundry added (default) · ghcr.io/wasp-foundry, pushed by the CI of wasp-foundry repos
NAME               VENDOR  ADDRESS               DEFAULT  STATUS
ghcr-wasp-foundry  ghcr    ghcr.io/wasp-foundry  yes      ready
```

- `--scm-connection` fills the vendor (`ghcr`), the host (`ghcr.io`) and the namespace (the org) once. The registry keeps no link to the connection: removing the connection leaves it.
- `--default` makes it the registry of every `build create` without `--registry`. Without a default registry, a build is refused with `NoDefaultRegistry`.
- The platform holds no registry credential: the CI pushes with its own `GITHUB_TOKEN`. The GitHub App of the connection cannot push nor pull on GHCR, which does not accept App tokens.
- `ready` means `https://ghcr.io/v2/` answers. Pulls are anonymous for now: the packages of `wasp-foundry` are public. A private package fails the deploy until the platform issues pull credentials (#367, #368).
- Adding, removing and changing the default is for `platform-admins`; anyone signed in lists them.

!!! note
    Without `--scm-connection`: `platform registry add ghcr-wasp-foundry --vendor ghcr --namespace wasp-foundry --default`. The reference is [Registries](../../reference/registries.md).
