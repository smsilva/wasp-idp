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

Open the home page, [http://hello-api.demo.localhost:7080/](http://hello-api.demo.localhost:7080/), in the browser:

- the version the branch built, `0.1.0-greetings.b5f9569`, next to its commit and the pod that answered;
- **Connected to PostgreSQL**, in green: the `db` the platform provisioned for this environment, its host, the server version and how long the query took;
- **Greets by name**, marked as new in this version: the change of the branch;
- **Open the API docs**: the Swagger UI of the app, where `GET /api/greet/{name}` can be tried.

The same from the terminal:

```bash
curl http://hello-api.demo.localhost:7080/api/greet/Ana
```

``` { .text .output title="output" }
{"message":"Hello, Ana!"}
```

```bash
curl http://hello-api.demo.localhost:7080/api/db
```

``` { .text .output title="output" }
{"status":"connected","host":"hello-api-db-6daaa09f.resources","port":5432,"database":"app","user":"app","serverVersion":"17.11","serverAddress":"10.42.0.62:5432","latencyMs":14.7,"error":null,"checkedAt":"2026-10-15T09:37:52.702202Z"}
```

When the database is unreachable, the page turns red with the error of the driver and `/api/db` answers `503`; `/healthz` stays `200`, so the pod is not restarted.
