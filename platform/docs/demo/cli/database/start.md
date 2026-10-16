# Bring it back

```bash
kubectl \
  --kubeconfig ~/.config/platform/environments/demo.kubeconfig \
  --namespace resources \
    scale statefulset \
      --selector app.kubernetes.io/name=postgres \
      --replicas 1
```

The page is green again in about 10 s. The Postgres has no volume: the seat of [Pick a seat](../deploy/seat.md) is gone.
