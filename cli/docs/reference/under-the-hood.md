# Under the hood

The CLI only talks to the Platform API. The API validates the token, writes each request as a CRD in `platform.wasp.silvios.me` (ADR 0022) and records it in the journal; the providers watch the CRDs and write the conditions.

```bash
kubectl get environments \
  --context k3d-platform-local \
  --namespace platform-system
```

``` { .text .output title="output" }
NAME   PROFILE     ACCOUNT   READY   REASON         EXPIRES
demo   shared                True    ClusterReady   2026-10-13T17:01:16Z
```

## Journal

One line before and one after applying each request. The `actor` is the token `sub`, which is immutable, followed by the e-mail. Credentials never reach the file.

```bash
kubectl exec deploy/platform-api \
  --context k3d-platform-local \
  --namespace platform-system \
  -- tail -n 2 /var/lib/platform/journal.jsonl
```

``` { .json .output title="output" }
{"id":"552d…","actor":"fe16e6a6-… (you@example.com)","action":"create","kind":"Environment","name":"demo","spec":{"profile":"ephemeral","expiresAt":"2026-10-13T17:01:16Z"},"applied":false}
{"id":"552d…","applied":true}
```

## Ports

| Port | Use |
|---|---|
| `6560` | Kubernetes API of `platform-local` |
| `127.0.0.1:9090` | Platform API |
| `localhost:8180` | Keycloak (issuer `http://localhost:8180/realms/platform`) |
| `127.0.0.1:7100`–`7119` | API of each environment (vcluster), one port per environment |
