# The CRD

```bash
kubectl get environments \
  --context k3d-platform-local \
  --namespace platform-system
```

```
NAME   PROFILE     READY   REASON         EXPIRES
demo   ephemeral   True    ClusterReady   2026-10-13T17:01:16Z
```

Journal dos pedidos (uma linha antes e outra depois de aplicar). O `actor` é o `sub` do token, imutável, seguido do e-mail:

```bash
kubectl exec deploy/platform-api \
  --context k3d-platform-local \
  --namespace platform-system \
  -- tail -n 2 /var/lib/platform/journal.jsonl
```

```json
{"id":"552d…","actor":"fe16e6a6-… (voce@example.com)","action":"create","kind":"Environment","name":"demo","spec":{"profile":"ephemeral","expiresAt":"2026-10-13T17:01:16Z"},"applied":false}
{"id":"552d…","applied":true}
```
