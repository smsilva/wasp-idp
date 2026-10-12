# Use the cluster

```bash
kubectl get nodes \
  --kubeconfig "${kubeconfig}"

kubectl create deployment web \
  --kubeconfig "${kubeconfig}" \
  --image nginx:alpine

kubectl auth whoami \
  --kubeconfig "${kubeconfig}"
```

The kubeconfig calls `platform environment credential greetings-test` on every command. `auth whoami` shows **your identity** in the vcluster: `system:serviceaccount:platform-identities:<sub>`.
