# Route a chain of calls

A route sends the calls made to a component's Service. When the instance it reaches calls another service, that second call is a new request: the mesh does not link it to the first one, so a header the first call carried is gone unless the service passes it on. A sandbox made of one changed service deep in a chain (`productpage` → `reviews`, with `reviews-pr-42` under test) needs that header on every hop.

The platform's contract is the OpenTelemetry Baggage: route by `--baggage`, and every service passes the `baggage` header on to the calls it makes while handling a request.

```bash
platform workload route \
  --component reviews \
  --environment demo \
  --baggage sandbox=pr-42 \
  --to reviews-pr-42
```

``` { .text .output title="output" }
✓ route of reviews in demo:
  baggage sandbox=pr-42 → reviews-pr-42
  otherwise → reviews
```

A call to `http://productpage` with `baggage: sandbox=pr-42` reaches the stable `productpage`, which calls `http://reviews` with the same baggage: that call goes to `reviews-pr-42`. Every other call, from the same `productpage`, goes to `reviews`. A route by `--header x-sandbox=pr-42` on `reviews` would not see the header at all: `productpage` does not pass `x-sandbox` on.

## What each service does

Services created from the `python-service` template already keep the contract: `app/telemetry.py` instruments FastAPI and `httpx` with OpenTelemetry, which reads `baggage` and `traceparent` from each request and writes them into every `httpx` call made while handling it. Call other services with `httpx`, never build those headers by hand.

Any other service keeps it with its language's OpenTelemetry instrumentation of the HTTP server and client, with the `tracecontext,baggage` propagators (the default). Without one, it copies the `baggage` header of the request into its outgoing calls itself.

One service that drops the baggage breaks the route silently: every call after it goes to the stable versions. The context also has to follow the work: a request handled across threads or tasks keeps its baggage only if the code carries the context along.
