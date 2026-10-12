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
INFO creating the gateway of env-greetings-test (*.greetings-test.localhost)
INFO environment greetings-test ready
env-greetings-test   Active   40s
```

Once the vcluster API is up, the provider installs the mesh in it: the Gateway API CRDs, `istio/base` and `istiod` (ADR 0035). Then it creates the environment's entry point (ADR 0036): a `Gateway` named `platform` in the vcluster, and an `Ingress` in `env-greetings-test` that sends `*.greetings-test.localhost` from the shared Traefik (`127.0.0.1:7080`) to it. The environment is `ready` only with `istiod` running and the `Gateway` programmed. Workloads go to namespace `apps`, which has sidecar injection.

```bash
curl --include http://anything.greetings-test.localhost:7080/
```

``` { .text .output title="output" }
HTTP/1.1 404 Not Found
server: istio-envoy
```

The `404` comes from the environment's gateway: no route takes the host yet. `*.localhost` resolves to the loopback without DNS.
