# Deploy and call it

The newest version built from the branch:

```bash
platform workload deploy \
  --component hello-api \
  --environment demo \
  --branch feat/greetings \
  --wait
```

``` { .text .output title="output" }
✓ hello-api@demo revision 1: 0.1.0-greetings.b5f9569 running · 1/1 replicas available
  url           http://hello-api.demo.localhost:7080/
  resource      db (postgres, provision): Ready
  resource      dns (dns, provision): Ready
  resource      route (route, provision): Ready
```

Call it from this machine:

```bash
curl --include http://hello-api.demo.localhost:7080/
```

``` { .text .output title="output" }
HTTP/1.1 200 OK
Content-Type: application/json
Server: istio-envoy

{"app":"hello-api","message":"hello"}
```
