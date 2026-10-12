# The provider inside

```bash
kubectl logs deploy/local-vcluster-provider \
  --context k3d-platform-local \
  --namespace platform-system \
  --tail 3

kubectl --context k3d-platform-local get namespaces | grep env-
```

``` { .text .output title="output" }
INFO creating vcluster env-greetings-test on port 7100
INFO installing the mesh in env-greetings-test (istio 1.30.5, gateway api v1.5.1)
INFO environment greetings-test ready
env-greetings-test   Active   40s
```

Once the vcluster API is up, the provider installs the mesh in it: the Gateway API CRDs, `istio/base` and `istiod` (ADR 0035). The environment is `ready` only with `istiod` running. Workloads go to namespace `apps`, which has sidecar injection.
