# Golden signals

The environment is observed from birth: each pod runs an Istio sidecar, and Prometheus scrapes it. The app needs no instrumentation. Send a minute of traffic, then read the four signals:

```bash
for i in $(seq 1 60); do curl --silent --output /dev/null http://hello-api.demo.localhost:7080/; sleep 1; done

platform workload signals \
  --component hello-api \
  --environment demo
```

``` { .text .output title="output" }
latency p95 0.47 ms · traffic 0.2 req/s · errors 0.00% · saturation 10.63%
```

- **latency p95, traffic, errors:** from the requests the sidecar saw, over the last 5 minutes.
- **saturation:** CPU or memory over the container's limit, on the busiest pod.
- **Too early:** the first values show about 30 s after the first requests. Before that, `no requests in window (5m)`.
