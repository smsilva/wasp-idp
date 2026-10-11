# JSON output

Every command accepts `--output json`:

```bash
platform environment list \
  --output json
```

``` { .json .output title="output" }
[
  {
    "name": "greetings-test",
    "profile": "ephemeral",
    "expiresAt": "2026-10-10T21:35:22Z",
    "status": "ready",
    "message": "vcluster running in namespace env-greetings-test, API on 127.0.0.1:7100",
    "port": 7100,
    "createdAt": "2026-10-10T20:35:22Z"
  }
]
```

Lists never include a kubeconfig; `platform environment get` returns it only to those who can use the environment. Errors keep one shape: `{"error": {"code", "message"}}`.

```bash
platform environment list --output json | jq -r '.[].name'
```
