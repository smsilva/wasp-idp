# Prerequisites

`platform init` needs Docker, k3d and kubectl on the `PATH`, and the CLI is installed with uv. Versions this walkthrough was last run with, on Ubuntu 24.04:

| Tool | Version | Check |
|---|---|---|
| Docker | 29.9.1 | `docker version --format '{{.Server.Version}}'` |
| k3d | v5.9.0 (k3s v1.35.5-k3s1) | `k3d version` |
| kubectl | v1.34.8 | `kubectl version --client` |
| uv | 0.11.7 | `uv --version` |
| git | 2.43.0 | `git --version` |
| gh | 2.45.0 | `gh --version` |

```bash
docker version --format '{{.Server.Version}}'

k3d version

kubectl version --client

uv --version

git --version

gh --version
```

git and gh come in later: the component steps clone the repo the platform creates, and the cleanup deletes it with `gh`.
