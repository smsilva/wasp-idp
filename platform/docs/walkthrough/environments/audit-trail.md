# Audit trail

```bash
kubectl exec deploy/platform-api \
  --context k3d-platform-local \
  --namespace platform-system \
  -- cat /var/lib/platform/journal.jsonl \
  | jq --compact-output 'select(.action) | {at, actor, action, name}'
```

``` { .json .output title="output" }
{"at":"2026-10-10T20:37:30+00:00","actor":"2016b176-… (you@example.com)","action":"create","name":"demo"}
{"at":"2026-10-10T20:38:45+00:00","actor":"2016b176-… (you@example.com)","action":"create","name":"checkin-test"}
```
