# Registries

```bash
platform registry add <registry> --scm-connection <connection> [--default]
platform registry add <registry> --vendor ghcr --namespace <org> [--host ghcr.io] [--default]
platform registry list
platform registry get <registry>
platform registry set-default <registry>
platform registry remove <registry>
```

An **OCI registry** is where a build pushes (ADR 0037): images today, Helm charts and other OCI artifacts later. The registry does not know what it holds; the `Version` of the index says what was published, and records the registry (`spec.registry`). The registry is chosen per build (`build create --registry`), never per component.

| Command | Who | What it does |
|---|---|---|
| `add` | `platform-admins` | registers a registry; `--scm-connection` fills `vendor`, `host` and `namespace` from a `github` connection (the GHCR of its org), once, without keeping a link to it; `--default` makes it the default and the previous default stops being it |
| `list`, `get` | anyone signed in | NAME, VENDOR, ADDRESS, DEFAULT, STATUS |
| `set-default` | `platform-admins` | the registry of every `build create` without `--registry` |
| `remove` | `platform-admins` | refused (`409`) while a version of the index is in it |

## Vendors

| Vendor | Host | Push | Pull |
|---|---|---|---|
| `ghcr` | `ghcr.io` (fixed) | the run's `GITHUB_TOKEN`, which writes only to the GHCR of the org that owns the repo: a build of a repo of another org is refused with `RegistryNotWritableByCI` | anonymous: the packages must be public |

The platform holds no registry credential. The GitHub App of an SCM connection cannot push nor pull on GHCR, which accepts only a classic PAT or a workflow's `GITHUB_TOKEN`. Harbor, ECR, ACR and GAR, the binding of registries to environments and the pull credentials issued per environment come next (#366 to #369).

## Status

The registry controller checks `https://<host>/v2/` every 5 minutes.

| Status | Meaning |
|---|---|
| `pending` | not checked yet |
| `ready` | `/v2/` answers `200`, or `401` with a token challenge (GHCR asks for a token even to read) |
| `Unreachable` | no answer, or an answer that is not an OCI registry; informative only: the CI pushes, so it does not block a build |

## Underneath

An `OCIRegistry` in `platform-system` (`kubectl --context k3d-platform-local --namespace platform-system get ociregistries`), written by the Platform API: at most one has `spec.default`. `platform init` creates none: registering the GHCR of the org is the admin's step after the [SCM connection](../walkthrough/scm-connection/registry.md).
