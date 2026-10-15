# Install the CLI

## Prerequisites

!!! validated "Validated on"
    Tested on the operating systems below.

    - Ubuntu 24.04.5 LTS, Docker Engine
    - macOS 26.5.2 on Apple Silicon, Colima 0.10.1

=== "Ubuntu"

    <div class="checks" markdown>

    | Tool | Version | Needed for | Check |
    |---|---|---|---|
    | Docker | 29.9.1 | init | `docker version --format '{{.Server.Version}}'` |
    | k3d | 5.9.0 | init | `k3d version` |
    | kubectl | 1.34.8 | init | `kubectl version --client` |
    | uv | 0.11.7 | install | `uv --version` |

    </div>

=== "macOS"

    <div class="checks" markdown>

    | Tool | Version | Needed for | Check |
    |---|---|---|---|
    | Colima | 0.10.1 | init | `colima version` |
    | Docker | 28.4.0 | init | `docker version --format '{{.Server.Version}}'` |
    | buildx | 0.32.0 | init | `docker buildx version` |
    | k3d | 5.9.0 | init | `k3d version` |
    | kubectl | 1.35.2 | init | `kubectl version --client` |
    | uv | 0.13.1 | install | `uv --version` |

    </div>

    Colima runs the Docker daemon, `docker buildx` is linked as a CLI plugin (`init` builds with the BuildKit-only `--provenance=false`) and the inotify limit is raised in Colima's VM: the steps are in [Prerequisites](../walkthrough/bootstrap/prerequisites.md).

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
| `make all` | `make cli` and `make mcp` (the MCP server, [MCP](mcp.md)) |
| `make` | lists the targets |

The install must be editable from the checkout: `init` applies CRDs, manifests and scripts versioned in the repo (or point `PLATFORM_REPO` to the checkout). It also builds the images of the API and the providers from the checkout on every run, so after a `git pull` running `platform init` again is enough: an unchanged image keeps its tag and is not rolled out again. Run `make all` again only when a `pyproject.toml` changes (a new dependency or command).

!!! note
    Without `make cli`, run the CLI from `cli/` with `uv run platform …`.
