# Prerequisites

!!! validated "Validated on"
    - Ubuntu 24.04.5 LTS, Docker Engine
    - macOS 26.5.2 on Apple Silicon, Colima 0.10.1

The k3d version is a minimum: `platform init` stops before doing anything when k3d is older than `5.9.0` (its default k3s image must be `v1.31` or newer). The other versions are the ones validated.

=== "Ubuntu"

    <div class="checks" markdown>

    | Tool | Version | Needed for | Check |
    |---|---|---|---|
    | Docker | 29.9.1 | init | `docker version --format '{{.Server.Version}}'` |
    | k3d | 5.9.0 | init | `k3d version` |
    | kubectl | 1.34.8 | init | `kubectl version --client` |
    | uv | 0.11.7 | install | `uv --version` |
    | git | 2.43.0 | components | `git --version` |
    | gh | 2.45.0 | cleanup | `gh --version` |

    </div>

=== "macOS"

    Where Docker Desktop is not allowed, [Colima](https://github.com/abiosoft/colima) runs the Docker daemon in a Linux VM. Every tool comes from Homebrew:

    ```bash
    brew install colima docker docker-buildx k3d kubernetes-cli uv git gh bash
    ```

    <div class="checks" markdown>

    | Tool | Version | Needed for | Check |
    |---|---|---|---|
    | Colima | 0.10.1 | init | `colima version` |
    | Docker | 28.4.0 | init | `docker version --format '{{.Server.Version}}'` |
    | buildx | 0.32.0 | init | `docker buildx version` |
    | k3d | 5.9.0 | init | `k3d version` |
    | kubectl | 1.35.2 | init | `kubectl version --client` |
    | uv | 0.13.1 | install | `uv --version` |
    | git | 2.53.0 | components | `git --version` |
    | gh | 2.92.0 | cleanup | `gh --version` |
    | bash | 5.3 | tests | `bash --version` |

    </div>

    The Homebrew `docker` formula is the CLI only, with no bundled BuildKit: `init` builds images with `docker build --provenance=false`, a BuildKit-only flag, so `docker buildx` must resolve or every build fails with `unknown flag: --provenance`. Link the plugin where the CLI finds it:

    ```bash
    mkdir -p ~/.docker/cli-plugins

    ln -sfn "$(brew --prefix)/opt/docker-buildx/bin/docker-buildx" ~/.docker/cli-plugins/docker-buildx
    ```

    Colima's default `fs.inotify.max_user_instances` (128) is too low for k3s's containerd once a second cluster shares the VM: its CRI plugin fails with `failed to create fsnotify watcher: too many open files`, and the node never reaches `Ready`. Raise it with a `provision` script in `~/.colima/default/colima.yaml`, which Colima applies on every start:

    ```yaml
    provision:
      - mode: system
        script: |
          sysctl -w fs.inotify.max_user_instances=8192
          sysctl -w fs.inotify.max_user_watches=524288
    ```

    Start Colima (4 CPUs and 8 GiB are enough for the control plane and one environment); after a change to `colima.yaml`, run `colima restart`:

    ```bash
    colima start --cpu 4 --memory 8 --disk 60
    ```

    - The repo scripts run with the first `bash` on the `PATH` (`#!/usr/bin/env bash`): they were validated with the Homebrew bash, not with the bash 3.2 of macOS.
    - Colima forwards the ports `init` maps on `127.0.0.1` (API, Keycloak, environments, ingress) to the Mac, with no setting.
