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
