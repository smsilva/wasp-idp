# Another instance of the same component

A pull request should run against the real services of the environment, next to the stable version, without taking its traffic. That is the shared sandbox: one more **instance** of the component in the same environment. `--instance` names it, and by default the instance is named after the component.

With `hello-api@demo` running `feat/greetings` again (the plan of [The plan of an environment](apply.md), applied without `--prune`), build a second branch in the clone of [Build a branch](../builds/create.md) and deploy it as `hello-api-pr-42`:

```bash
git -C /tmp/hello-api switch --create feat/farewell main

echo "Says goodbye." >> /tmp/hello-api/README.md

git -C /tmp/hello-api commit --all --message "feat: say goodbye"

git -C /tmp/hello-api push --set-upstream origin feat/farewell

platform build create \
  --component hello-api \
  --branch feat/farewell \
  --wait

platform workload deploy \
  --component hello-api \
  --instance hello-api-pr-42 \
  --environment demo \
  --branch feat/farewell \
  --wait

platform workload list \
  --environment demo
```

``` { .text .output title="output" }
building from feat/farewell @ 910ace9 …
✓ app-spec.yaml valid · db (postgres), dns, route
✓ image hello-api:0.1.0-farewell.910ace9 pushed to ghcr-wasp-foundry (ghcr.io/wasp-foundry/hello-api)
✓ hello-api-pr-42@demo revision 1: 0.1.0-farewell.910ace9 running · 1/1 replicas available
  url           http://hello-api-pr-42.demo.localhost:7080/
  resource      db (postgres, provision): Ready
  resource      dns (dns, provision): Ready
  resource      route (route, provision): Ready
WORKLOAD              COMPONENT  VERSION                  STATUS     REPLICAS  REVISION  TRAFFIC  URL
hello-api@demo        hello-api  0.1.0-greetings.b5f9569  Available  2/2       6         —        http://hello-api.demo.localhost:7080/
hello-api-pr-42@demo  hello-api  0.1.0-farewell.910ace9   Available  1/1       1         —        http://hello-api-pr-42.demo.localhost:7080/
```

- Each instance has a Deployment and a Service of its own. The Service `hello-api` selects only the pods of the instance `hello-api`, so the pull request gets no traffic from it. You reach it by its own URL, `http://hello-api-pr-42.demo.localhost:7080/`, or inside the environment by its own Service, `http://hello-api-pr-42.apps`, until a [route](route.md) sends it calls made to `http://hello-api`.
- Its revisions, its history and its resources are its own: a `provision` database is one per instance, and its `dns` gives it a host of its own.
- The first deploy names the component of the instance, and the instance keeps it. A deploy that names another component is refused (`409`), and so is an instance named like another component: its Service would answer for it.

`get`, `signals`, `rollback` and `remove` take the instance as an argument: `hello-api-pr-42` with `--environment`, or `hello-api-pr-42@demo` alone, the name `list` prints in its `WORKLOAD` column. The default instance is named after its component, so `hello-api` stays `hello-api`:

```bash
platform workload get hello-api-pr-42@demo
```

`history --component` lists every instance of the component, and `history --instance` lists only one:

```bash
platform workload history \
  --environment demo \
  --component hello-api

platform workload remove hello-api-pr-42 \
  --environment demo \
  --wait
```

``` { .text .output title="output" }
WORKLOAD              REVISION  ACTION    VERSION                  STATUS                 BY               CREATED
hello-api@demo        1         deploy    0.1.0-greetings.b5f9569  Succeeded              dev@example.com  2026-10-12T19:02:42Z
…
hello-api@demo        6         deploy    0.1.0-greetings.b5f9569  Succeeded              dev@example.com  2026-10-12T19:04:49Z
hello-api-pr-42@demo  1         deploy    0.1.0-farewell.910ace9   Succeeded              dev@example.com  2026-10-12T19:06:32Z
✓ hello-api-pr-42@demo revision 2: removed from demo
```

In the plan of the environment, an extra instance is a key with `component:`:

```yaml
environment: demo
workloads:
  hello-api:
    branch: feat/greetings
    replicas: 2
  hello-api-pr-42:
    component: hello-api
    branch: feat/farewell
```

`platform catalog component get hello-api` lists it in `running in` as `hello-api-pr-42@demo`. The default instance still shows by its environment alone.
