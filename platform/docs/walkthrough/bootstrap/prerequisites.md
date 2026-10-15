# Prerequisites

!!! validated "Validated on"
    - Ubuntu 24.04.5 LTS

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

!!! note "macOS without Docker Desktop"
    Where Docker Desktop is not allowed, [Colima](https://github.com/abiosoft/colima) provides the
    daemon instead:

    ```bash
    brew install colima docker docker-buildx docker-compose k3d kubectl uv

    colima start --cpu 4 --memory 8 --disk 60
    ```

    The Homebrew `docker` formula is the CLI only, with no bundled BuildKit: `init` builds images
    with `docker build --provenance=false`, a BuildKit-only flag, so `docker buildx` must resolve
    or every build fails with `unknown flag: --provenance`.

    ```bash
    mkdir -p ~/.docker/cli-plugins
    ln -sfn "$(brew --prefix)/opt/docker-buildx/bin/docker-buildx" ~/.docker/cli-plugins/docker-buildx
    docker buildx version
    ```

    Colima's default `fs.inotify.max_user_instances` (128) is too low for k3s's containerd once a
    second cluster shares the VM: its CRI plugin fails to start with `failed to create cni conf
    monitor: failed to create fsnotify watcher: too many open files`, and the node never reaches
    `Ready` (`kubectl get nodes` reports none). Raise it with a `provision` script in
    `~/.colima/default/colima.yaml`, which Colima re-applies on every start:

    ```yaml
    provision:
      - mode: system
        script: |
          sysctl -w fs.inotify.max_user_instances=8192
          sysctl -w fs.inotify.max_user_watches=524288
    ```

    Apply it once with `colima restart`.
