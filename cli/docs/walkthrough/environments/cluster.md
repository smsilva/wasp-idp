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

The kubeconfig calls `platform environment credential demo` on every command. `auth whoami` shows **your identity** in the vcluster: `system:serviceaccount:platform-identities:<sub>`.

You are `cluster-admin` in the vcluster, but a pod cannot reach the host: `hostNetwork`, `privileged`, `hostPath` and the rest of the Pod Security Standard `baseline` are refused at apply. The list is in [What a pod may not do](../../reference/environments.md#what-a-pod-may-not-do).
