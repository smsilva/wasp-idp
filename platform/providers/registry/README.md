# registry provider

Checks that each `OCIRegistry` (`platform.wasp.silvios.me`, ADR 0037) answers the OCI Distribution API: `GET https://<host>/v2/` returning `200`, or `401` with a `WWW-Authenticate` challenge, sets `Ready` `Verified`; anything else is `Unreachable`. The CI pushes, so the status never blocks a build. Pull credentials per environment come with #367.

```bash
uv sync
uv run pytest
uv run registry-provider --context k3d-platform-local
```

`platform init` builds the image, imports it into `platform-local` and applies `deploy/registry-provider.yaml`.
