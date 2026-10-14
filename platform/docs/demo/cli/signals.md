# Golden signals

A minute of traffic:

```bash
for i in $(seq 1 60); do
  curl \
    --silent \
    --output /dev/null \
    http://hello-api.demo.localhost:7080/

  sleep 1
done
```

The four signals, with no instrumentation in the app:

```bash
platform workload signals hello-api \
  --environment demo
```

``` { .text .output title="output" }
latency p95 0.47 ms · traffic 0.98 req/s · errors 0.00% · saturation 10.63%
```
