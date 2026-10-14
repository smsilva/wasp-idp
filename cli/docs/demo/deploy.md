# Deploy and call it

Deploy the newest version built from the branch, and call it from this machine:

```bash
platform workload deploy \
  --component hello-api \
  --environment demo \
  --branch feat/greetings \
  --wait

curl --include http://hello-api.demo.localhost:7080/
```

``` { .text .output title="output" }
✓ hello-api@demo revision 1: 0.1.0-greetings.b5f9569 running · 1/1 replicas available
  url           http://hello-api.demo.localhost:7080/
  resource      db (postgres, provision): Ready
  resource      dns (dns, provision): Ready
  resource      route (route, provision): Ready
HTTP/1.1 200 OK
Content-Type: application/json
Server: istio-envoy

{"app":"hello-api","message":"hello"}
```

- **Resources:** the platform read the `app-spec.yaml` and made what it asks for: a Postgres, a host and a route. The app declares *what* it needs, never *how*.
- **Revision:** each deploy is a revision, and the version is pinned in it by digest. `platform workload rollback` goes back one.
- **URL:** `*.localhost` resolves to this machine, with no `port-forward`.
