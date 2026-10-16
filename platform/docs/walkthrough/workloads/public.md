# Reach an instance from outside

Every environment has an entry point at `http://*.<environment>.localhost:7080` ([The provider inside](../environments/provider.md)). A Score with a `dns` and a `route` takes a host under it. The `app-spec.yaml` of the golden path `python-service` has both, which is why the `seat-selection` of [Deploy a version to an environment](deploy.md) answered `curl` with no extra step:

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
service:
  ports:
    http:
      port: 80
      targetPort: 8000
```

``` { .text .output title="output" }
✓ seat-selection@demo revision 1: 0.1.0-seat-pick.b5f9569 running · 2/2 replicas available
  url           http://seat-selection.demo.localhost:7080/
  resource      dns (dns, provision): Ready
  resource      route (route, provision): Ready
```

- The `dns` gives the instance its host, `seat-selection.demo.localhost`. The `route` takes it from `${resources.dns.host}` and writes an `HTTPRoute` on the `Gateway` of the environment, to port `80` of the instance's Service.
- `workload list` shows the public URL in the `URL` column; `get` shows it as `url`, next to the `internal url` the other workloads of the environment use. A Score without a `route` has only the internal one.
- `*.localhost` resolves to the loopback without DNS: no `/etc/hosts`, and no `kubectl port-forward`.
- Each instance gets its own host: the `seat-selection-pr-42` of [Another instance of the same component](instances.md) answers at `http://seat-selection-pr-42.demo.localhost:7080/`.
- A `route` only takes the host of its own instance (`seat-selection.demo.localhost` or a name under it). Another host ends the revision as `ResourcesFailed`.
- `workload remove` deletes the `HTTPRoute` once the Forager releases the `route` (up to its 30 s resync), and the same URL answers `404` from the `Gateway`. In between it answers `500`: the Service of the instance is already gone.
