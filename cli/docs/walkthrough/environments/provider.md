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
INFO environment greetings-test ready
env-greetings-test   Active   40s
```
