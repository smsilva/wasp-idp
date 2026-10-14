# Install the CLI

## Prerequisites

| Tool | Check |
|---|---|
| Docker | `docker version --format '{{.Server.Version}}'` |
| k3d | `k3d version` |
| kubectl | `kubectl version --client` |
| uv | `uv --version` |

## Install

From the repo root:

```bash
make cli

platform --help
```

| Target | What it does |
|---|---|
| `make cli` | `uv tool install --force --editable cli/`: puts `platform` on the `PATH`, pointing to this checkout; running it from another checkout switches to that one |
| `make cli-uninstall` | removes `platform` from the `PATH` |
| `make` | lists the targets |

The install must be editable from the checkout: `init` applies CRDs, manifests and scripts versioned in the repo (or point `PLATFORM_REPO` to the checkout).

!!! note
    Without `make cli`, run the CLI from `cli/` with `uv run platform …`.
