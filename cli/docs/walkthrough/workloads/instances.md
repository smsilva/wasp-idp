# Another instance of the same component

A pull request should run against the real services of the environment, next to the stable version, without taking its traffic. That is the shared sandbox: one more **instance** of the component in the same environment. `--instance` names it, and by default the instance is named after the component.

```bash
platform workload deploy \
  --component hello-api \
  --instance hello-api-pr-42 \
  --environment demo \
  --branch feat/greetings \
  --wait

platform workload list \
  --environment demo
```

``` { .text .output title="output" }
✓ hello-api-pr-42@demo revision 1: 0.4.0-greetings.4444444 running · 1/1 replicas available
WORKLOAD              COMPONENT  VERSION                  STATUS     REPLICAS  REVISION  URL
hello-api@demo        hello-api  0.3.0                    Available  2/2       1         http://hello-api.apps:80
hello-api-pr-42@demo  hello-api  0.4.0-greetings.4444444  Available  1/1       1         http://hello-api-pr-42.apps:80
```

- Each instance has a Deployment and a Service of its own. The Service `hello-api` selects only the pods of the instance `hello-api`, so the pull request gets no traffic from it. You reach it by its own Service, `http://hello-api-pr-42.apps`. Routing a request to it by header is phase 3.
- Its revisions, its history and its resources are its own: a `provision` database is one per instance.
- The first deploy names the component of the instance, and the instance keeps it. A deploy that names another component is refused (`409`), and so is an instance named like another component: its Service would answer for it.

With two instances, `--component` is no longer enough to pick one:

```bash
platform workload get \
  --component hello-api \
  --environment demo
```

``` { .text .output title="output" }
✗ hello-api has 2 instances in demo: hello-api, hello-api-pr-42; give --instance
```

`get`, `rollback` and `remove` take `--instance`. `history --component` lists every instance of the component, and `history --instance` lists only one:

```bash
platform workload history \
  --environment demo \
  --component hello-api

platform workload remove \
  --instance hello-api-pr-42 \
  --environment demo \
  --wait
```

``` { .text .output title="output" }
WORKLOAD              REVISION  ACTION  VERSION                  STATUS     BY                CREATED
hello-api@demo        1         deploy  0.3.0                    Succeeded  dev@example.com   2026-10-11T12:00:00Z
hello-api-pr-42@demo  1         deploy  0.4.0-greetings.4444444  Succeeded  dev@example.com   2026-10-11T12:05:00Z
✓ hello-api-pr-42@demo revision 2: removed from demo
```

In the plan of the environment, an extra instance is a key with `component:`:

```yaml
environment: demo
workloads:
  hello-api:
    version: 0.3.0
    replicas: 2
  hello-api-pr-42:
    component: hello-api
    branch: feat/greetings
```

`platform catalog component get hello-api` lists it in `running in` as `hello-api-pr-42@demo`. The default instance still shows by its environment alone.
