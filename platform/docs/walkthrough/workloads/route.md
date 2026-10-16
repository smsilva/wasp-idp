# Route traffic to an instance

An extra instance gets no traffic from its component's Service until a **route** sends it some. `workload route` splits the calls made to `http://seat-selection` inside the environment: by header, by an OpenTelemetry Baggage entry, or by weight. The environment's mesh (Istio, one per environment) applies it as a Gateway API `HTTPRoute`.

```bash
platform workload route \
  --component seat-selection \
  --environment demo \
  --header x-sandbox=pr-42 \
  --to seat-selection-pr-42

platform workload list \
  --environment demo
```

``` { .text .output title="output" }
✓ route of seat-selection in demo:
  x-sandbox=pr-42 → seat-selection-pr-42
  otherwise → seat-selection
WORKLOAD                   COMPONENT       VERSION                  STATUS     REPLICAS  REVISION  TRAFFIC          URL
seat-selection@demo        seat-selection  0.1.0-seat-pick.b5f9569  Available  2/2       6         default          http://seat-selection.demo.localhost:7080/
seat-selection-pr-42@demo  seat-selection  0.1.0-farewell.910ace9   Available  1/1       1         x-sandbox=pr-42  http://seat-selection-pr-42.demo.localhost:7080/
```

A call to `http://seat-selection` with `x-sandbox: pr-42` reaches the pull request; any other call reaches the stable version. The route takes effect in about a second. Only calls from pods in the namespace `apps` go through the mesh, and the header only travels further down a chain of calls if each service passes it on.

`--baggage sandbox=pr-42` matches the entry `sandbox=pr-42` of the `baggage` header instead, which OpenTelemetry passes on by itself: it is the one that holds down a chain of calls ([Route a chain of calls](baggage.md)). `--weight` is the canary: a percentage of the calls that no header or baggage rule took.

```bash
platform workload route \
  --component seat-selection \
  --environment demo \
  --weight 10 \
  --to seat-selection-pr-42
```

``` { .text .output title="output" }
✓ route of seat-selection in demo:
  x-sandbox=pr-42 → seat-selection-pr-42
  seat-selection-pr-42 10% · seat-selection 90%
```

Each `route` changes one rule and keeps the others: the same header again replaces its rule, and `--weight 0` takes an instance out of the weights. While a route sends traffic to an instance, removing it is refused, and so is removing `seat-selection` while it has a route at all:

```bash
platform workload remove seat-selection-pr-42 \
  --environment demo
```

``` { .text .output title="output" }
✗ 409: remove of seat-selection-pr-42@demo: the route of 'seat-selection' sends traffic to it; change the route first
```

`--clear` removes the route, and every call goes to `seat-selection` again:

```bash
platform workload route \
  --component seat-selection \
  --environment demo \
  --clear
```

``` { .text .output title="output" }
✓ route of seat-selection in demo cleared: every request goes to seat-selection
```
