# Check the database

```bash
curl http://seat-selection.demo.localhost:7080/api/db
```

``` { .text .output title="output" }
{"status":"connected","host":"seat-selection-db-6daaa09f.resources","port":5432,"database":"app","user":"app","serverVersion":"17.11","latencyMs":14.7,"details":true}
```

The same check as the home page. [Stop the database](../database/stop.md) to see it fail.
