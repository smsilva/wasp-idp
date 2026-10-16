# Stop the database

```bash
kubectl \
  --kubeconfig ~/.config/platform/environments/demo.kubeconfig \
  --namespace resources \
    scale statefulset \
      --selector app.kubernetes.io/name=postgres \
      --replicas 0
```

The Postgres of <span class="t-environment">demo</span> runs in its vcluster: the kubeconfig comes from `platform environment get demo`.
