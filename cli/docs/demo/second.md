# A second environment

The same version, in a second environment. `greetings-test` is `ephemeral`, so its database goes to the shared Postgres instead of one of its own, with no change to the app:

```bash
platform environment create greetings-test \
  --profile ephemeral \
  --expires 2h \
  --wait

platform workload deploy \
  --component hello-api \
  --environment greetings-test \
  --branch feat/greetings \
  --wait

curl --include http://hello-api.greetings-test.localhost:7080/
```

``` { .text .output title="output" }
✓ greetings-test ready
✓ hello-api@greetings-test revision 1: 0.1.0-greetings.b5f9569 running · 1/1 replicas available
  url           http://hello-api.greetings-test.localhost:7080/
  resource      db (postgres, compose): Ready
  resource      dns (dns, provision): Ready
  resource      route (route, provision): Ready
HTTP/1.1 200 OK
Content-Type: application/json
Server: istio-envoy

{"app":"hello-api","message":"hello"}
```

- **`db (postgres, compose)`:** the profile's policy put the database in the shared instance. In `demo` it was `provision`.
- **Where the app runs:** `platform catalog component get hello-api` now lists both environments under `running in`.
