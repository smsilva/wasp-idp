# Prerequisites

!!! validated "Validated on"
    - Ubuntu 24.04.5 LTS, Docker Engine
    - macOS 26.5.2 on Apple Silicon, Colima 0.10.1

=== "Ubuntu"

    <div class="checks" markdown>

    | Tool | Version | Needed for | Check |
    |---|---|---|---|
    | AWS CLI | >= 2.34.30 | cloud accounts (optional) | `aws --version` |
    | Claude Code | >= 2.1.301 | agents (optional) | `claude --version` |
    | curl | >= 8.5.0 | environments, workloads | `curl --version` |
    | Docker | >= 29.9.1 | init | `docker version --format '{{.Server.Version}}'` |
    | gh | >= 2.102.0 | cleanup | `gh --version` |
    | git | >= 2.43.0 | components | `git --version` |
    | k3d | >= 5.9.0 | init | `k3d version` |
    | kubectl | >= 1.34.8 | init | `kubectl version --client` |
    | Helm | >= 3.14.0 | init | `helm version --short` |
    | make | >= 4.3 | install | `make --version` |
    | Python | >= 3.14.4 | install | `python3 --version` |
    | uv | >= 0.11.7 | install | `uv --version` |

    </div>

    The CLI and the MCP server declare `requires-python = ">=3.11"`: `uv tool install` uses the system Python when it satisfies that range, and downloads one only when it does not.

=== "macOS"

    Where Docker Desktop is not allowed, [Colima](https://github.com/abiosoft/colima) runs the Docker daemon in a Linux VM. Every tool comes from Homebrew:

    ```bash
    brew install colima docker docker-buildx k3d kubernetes-cli uv git gh bash helm
    ```

    <div class="checks" markdown>

    | Tool | Version | Needed for | Check |
    |---|---|---|---|
    | bash | >= 5.3 | tests | `bash --version` |
    | buildx | >= 0.32.0 | init | `docker buildx version` |
    | Colima | >= 0.10.1 | init | `colima version` |
    | Docker | >= 28.4.0 | init | `docker version --format '{{.Server.Version}}'` |
    | gh | >= 2.92.0 | cleanup | `gh --version` |
    | git | >= 2.53.0 | components | `git --version` |
    | k3d | >= 5.9.0 | init | `k3d version` |
    | kubectl | >= 1.35.2 | init | `kubectl version --client` |
    | Helm | >= 3.14.0 | init | `helm version --short` |
    | uv | >= 0.13.1 | install | `uv --version` |

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
