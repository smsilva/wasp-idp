# Expiration

Ambientes com `--expires` são apagados pelo provider quando o prazo vence (checado a cada 10 s):

```bash
platform environment create short-lived \
  --profile ephemeral \
  --expires 1m
```

```bash
kubectl --context k3d-platform-local --namespace platform-system logs deploy/local-vcluster-provider
```

```
INFO environment short-lived expired at 2026-10-10T21:38:44Z, deleting
INFO deleting vcluster env-short-lived
INFO environment short-lived removed
```

Formatos de `--expires`: `30m`, `12h`, `3d`, `1w`.
