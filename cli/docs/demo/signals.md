# Golden signals

A minute of traffic:

```bash
for i in $(seq 1 60); do curl --silent --output /dev/null http://hello-api.demo.localhost:7080/; sleep 1; done
```

The four signals, with no instrumentation in the app:

```bash
platform workload signals \
  --component hello-api \
  --environment demo
```
