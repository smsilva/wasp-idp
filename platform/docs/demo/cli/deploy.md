# Deploy and call it

The newest version built from the branch:

```bash
platform workload deploy \
  --component seat-selection \
  --environment demo \
  --branch feat/seat-pick \
  --wait
```

``` { .text .output title="output" }
✓ seat-selection@demo revision 1: 0.1.0-seat-pick.b5f9569 running · 1/1 replicas available
  url           http://seat-selection.demo.localhost:7080/
  resource      db (postgres, provision): Ready
  resource      dns (dns, provision): Ready
  resource      route (route, provision): Ready
```

Open the home page, [http://seat-selection.demo.localhost:7080/](http://seat-selection.demo.localhost:7080/), in the browser:

- the version the branch built, `0.1.0-seat-pick.b5f9569`, next to its commit and the pod that answered;
- **Connected to PostgreSQL**, in green: the `db` the platform provisioned for this environment, its host, the server version and how long the query took;
- **Picks a seat at check-in**, marked as new in this version: the change of the branch;
- **Open the API docs**: the Swagger UI of the app, where `PUT /api/bookings/{booking}/passengers/{passenger}/seat` can be tried.

The same from the terminal:

```bash
curl \
  --request PUT \
  --header "Content-Type: application/json" \
  --data '{"seat": "12A"}' \
  http://seat-selection.demo.localhost:7080/api/bookings/TW4821/passengers/1/seat
```

``` { .text .output title="output" }
{"booking":"TW4821","passenger":"1","seat":"12A","status":"held"}
```

```bash
curl http://seat-selection.demo.localhost:7080/api/db
```

``` { .text .output title="output" }
{"status":"connected","host":"seat-selection-db-6daaa09f.resources","port":5432,"database":"app","user":"app","serverVersion":"17.11","serverAddress":"10.42.0.62:5432","latencyMs":14.7,"checkedAt":"2026-10-15T09:37:52.702202Z","details":true}
```

When the database is unreachable, the page turns red with the error of the driver and `/api/db` answers `503`; `/healthz` stays `200`, so the pod is not restarted.
