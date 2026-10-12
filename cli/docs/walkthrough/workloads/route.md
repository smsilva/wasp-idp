# Route traffic to an instance

An extra instance gets no traffic from its component's Service until a **route** sends it some. `workload route` splits the calls made to `http://hello-api` inside the environment: by header, by an OpenTelemetry Baggage entry, or by weight. The environment's mesh (Istio, one per environment) applies it as a Gateway API `HTTPRoute`.

```bash
platform workload route \
  --component hello-api \
  --environment demo \
  --header x-sandbox=pr-42 \
  --to hello-api-pr-42

platform workload list \
  --environment demo
```

``` { .text .output title="output" }
✓ route of hello-api in demo:
  x-sandbox=pr-42 → hello-api-pr-42
  otherwise → hello-api
WORKLOAD              COMPONENT  VERSION                  STATUS     REPLICAS  REVISION  TRAFFIC          URL
hello-api@demo        hello-api  0.3.0                    Available  2/2       1         default          http://hello-api.apps:80
hello-api-pr-42@demo  hello-api  0.4.0-greetings.4444444  Available  1/1       1         x-sandbox=pr-42  http://hello-api-pr-42.apps:80
```

A call to `http://hello-api` with `x-sandbox: pr-42` reaches the pull request; any other call reaches the stable version. The route takes effect in about a second. Only calls from pods in the namespace `apps` go through the mesh, and the header only travels further down a chain of calls if each service passes it on.

`--baggage sandbox=pr-42` matches the entry `sandbox=pr-42` of the `baggage` header instead, which OpenTelemetry passes on by itself. `--weight` is the canary: a percentage of the calls that no header or baggage rule took.

```bash
platform workload route \
  --component hello-api \
  --environment demo \
  --weight 10 \
  --to hello-api-pr-42
```

``` { .text .output title="output" }
✓ route of hello-api in demo:
  x-sandbox=pr-42 → hello-api-pr-42
  hello-api-pr-42 10% · hello-api 90%
```

Each `route` changes one rule and keeps the others: the same header again replaces its rule, and `--weight 0` takes an instance out of the weights. While a route sends traffic to an instance, removing it is refused, and so is removing `hello-api` while it has a route at all:

```bash
platform workload remove \
  --instance hello-api-pr-42 \
  --environment demo
```

``` { .text .output title="output" }
✗ 409: remove of hello-api-pr-42@demo: the route of 'hello-api' sends traffic to it; change the route first
```

`--clear` removes the route, and every call goes to `hello-api` again:

```bash
platform workload route \
  --component hello-api \
  --environment demo \
  --clear
```

``` { .text .output title="output" }
✓ route of hello-api in demo cleared: every request goes to hello-api
```
