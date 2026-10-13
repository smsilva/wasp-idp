# The registry is ready

Either way, the platform now has one registry:

```bash
platform registry list
```

``` { .text .output title="output" }
NAME               VENDOR  ADDRESS               DEFAULT  STATUS
ghcr-wasp-foundry  ghcr    ghcr.io/wasp-foundry  yes      ready
```

| Field | What it means |
|---|---|
| `DEFAULT` | `--default` makes it the registry of every `build create` without `--registry`. With no default, a build is refused with `NoDefaultRegistry`. |
| `STATUS` | `ready` means `https://ghcr.io/v2/` answers. |

!!! info "Credentials"
    The platform holds no registry credential. The CI pushes with its own `GITHUB_TOKEN`; the GitHub App of the connection does not help here, since GHCR does not accept App tokens. Pulls are anonymous for now, so the packages of `wasp-foundry` must be public: a private package fails the deploy until the platform issues pull credentials (#367, #368).

Anyone signed in lists the registries.
