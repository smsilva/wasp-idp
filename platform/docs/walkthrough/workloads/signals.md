# The golden signals of an instance

The environment was born observed: each pod in `apps` runs an Istio sidecar, and the Prometheus that `platform init` installs in `platform-local` scrapes them all ([ADR 0040](https://github.com/smsilva/wasp-idp/blob/main/docs/adr/0040-platform-local-prometheus-scraping-vcluster-sidecars.md)). The app needs no instrumentation. Send some traffic to the `seat-selection` of [Reach an instance from outside](public.md), then read its four signals (the output below is from the `cli-e2e` run, with a `/status/500` every ten requests):

```bash
for i in $(seq 1 60); do curl --silent --output /dev/null http://seat-selection.demo.localhost:7080/; sleep 1; done
platform workload signals seat-selection --environment demo
```

``` { .text .output title="output" }
latency p95 0.47 ms · traffic 0.2 req/s · errors 9.09% · saturation 10.63%
```

- **latency p95** and **traffic** count the requests the instance received through its sidecar, from outside (through the environment's entry point) and from the other workloads of the environment.
- **errors** is the share of those requests answered with a `5xx`.
- **saturation** is the higher of CPU and memory usage over the container's limit, on the busiest pod. The sidecar is left out. The `app-spec.yaml` of `python-service` declares `resources.limits` for that reason: without a limit, saturation shows `— (no CPU or memory limit declared)`.
- The signals look at the last 5 minutes. `--window 1h` looks further back, up to `6h`, which is how long Prometheus keeps them.
- The first signals show up about 30 s after the first requests: Prometheus scrapes every 15 s, and a rate needs two samples. Until then you get `latency p95 — · traffic 0 req/s · errors —` and the line `no requests in window (5m)`.
- The sidecar creates each series (one per response code, per caller) on its first request. A burst that ends before Prometheus has scraped that series twice leaves a counter that never grows, so it does not count: the loop above lasts a minute for that reason.

With `--output json`, the same values as numbers, with errors and saturation as fractions:

```bash
platform workload signals seat-selection --environment demo --output json
```

``` { .json .output title="output" }
{
  "kind": "WorkloadSignals",
  "name": "seat-selection@demo",
  "environment": "demo",
  "instance": "seat-selection",
  "window": "5m",
  "latencyP95Ms": 0.475,
  "trafficRps": 0.2003,
  "errorRate": 0.0909,
  "saturation": {"value": 0.1063, "cpu": 0.0007, "memory": 0.1063, "reason": null},
  "message": null
}
```
