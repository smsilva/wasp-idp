# Reach an instance from outside

Every environment has an entry point at `http://*.<environment>.localhost:7080` ([The provider inside](../environments/provider.md)). A Score with a `dns` and a `route` takes a host under it, the same way the golden path `python-service` does:

```yaml
resources:
  dns:
    type: dns
  route:
    type: route
    params:
      host: ${resources.dns.host}
      path: /
      port: 80
containers:
  app:
    image: .
service:
  ports:
    http:
      port: 80
      targetPort: 9898
```

With a version `0.6.0` of `hello-api` with that Score and the public image `podinfo` (written by `kubectl` as in [The spec of a version](spec.md)):

```bash
platform workload deploy \
  --component hello-api \
  --environment demo \
  --version 0.6.0 \
  --wait

platform workload get \
  --component hello-api \
  --environment demo

curl http://hello-api.demo.localhost:7080/
```

``` { .text .output title="output" }
✓ hello-api@demo revision 14: 0.6.0 running · 1/1 replicas available
  url           http://hello-api.demo.localhost:7080/
  resource      dns (dns, provision): Ready
  resource      route (route, provision): Ready
hello-api@demo (Available)
  component     hello-api
  version       0.6.0
  image         ghcr.io/stefanprodan/podinfo@sha256:862ca45e61b32392f7941a1bdfdbe5ff8b6899070135f1bdca1c287d0057fc94
  replicas      1/1
  revision      14
  traffic       —
  url           http://hello-api.demo.localhost:7080/
  internal url  http://hello-api.apps:80
  message       1/1 replicas ready
  resource      dns (dns, provision): Ready
  resource      route (route, provision): Ready
{
  "hostname": "hello-api-d77ff4d8c-l6qft",
  "version": "6.7.1",
  …
}
```

- The `dns` gives the instance its host, `hello-api.demo.localhost`. The `route` takes it from `${resources.dns.host}` and writes an `HTTPRoute` on the `Gateway` of the environment.
- `workload list` shows the public URL in the `URL` column; `get` shows it as `url`, next to the `internal url` the other workloads of the environment use.
- `*.localhost` resolves to the loopback without DNS: no `/etc/hosts`, and no `kubectl port-forward`.
- A `route` only takes the host of its own instance (`hello-api.demo.localhost` or a name under it). Another host ends the revision as `ResourcesFailed`.
- `workload remove` deletes the `HTTPRoute` once the Forager releases the `route` (up to its 30 s resync), and the same URL answers `404` from the `Gateway`. In between it answers `500`: the Service of the instance is already gone.
