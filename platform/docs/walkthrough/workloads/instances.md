# Another instance of the same component

A pull request should run against the real services of the environment, next to the stable version, without taking its traffic. That is the shared sandbox: one more **instance** of the component in the same environment. `--instance` names it, and by default the instance is named after the component.

With `seat-selection@demo` running `feat/seat-pick` again (the plan of [The plan of an environment](apply.md), applied without `--prune`), build a second branch in the clone of [Build a branch](../builds/create.md) and deploy it as `seat-selection-pr-42`:

```bash
git -C /tmp/seat-selection switch --create feat/farewell main

echo "Says goodbye." >> /tmp/seat-selection/README.md

git -C /tmp/seat-selection commit --all --message "feat: say goodbye"

git -C /tmp/seat-selection push --set-upstream origin feat/farewell

platform build create \
  --component seat-selection \
  --branch feat/farewell \
  --wait

platform workload deploy \
  --component seat-selection \
  --instance seat-selection-pr-42 \
  --environment demo \
  --branch feat/farewell \
  --wait

platform workload list \
  --environment demo
```

``` { .text .output title="output" }
building from feat/farewell @ 910ace9 …
✓ app-spec.yaml valid · db (postgres), dns, route
✓ image seat-selection:0.1.0-farewell.910ace9 pushed to ghcr-wasp-foundry (ghcr.io/wasp-foundry/seat-selection)
✓ seat-selection-pr-42@demo revision 1: 0.1.0-farewell.910ace9 running · 1/1 replicas available
  url           http://seat-selection-pr-42.demo.localhost:7080/
  resource      db (postgres, provision): Ready
  resource      dns (dns, provision): Ready
  resource      route (route, provision): Ready
WORKLOAD                   COMPONENT       VERSION                  STATUS     REPLICAS  REVISION  TRAFFIC  URL
seat-selection@demo        seat-selection  0.1.0-seat-pick.b5f9569  Available  2/2       6         —        http://seat-selection.demo.localhost:7080/
seat-selection-pr-42@demo  seat-selection  0.1.0-farewell.910ace9   Available  1/1       1         —        http://seat-selection-pr-42.demo.localhost:7080/
```

- Each instance has a Deployment and a Service of its own. The Service `seat-selection` selects only the pods of the instance `seat-selection`, so the pull request gets no traffic from it. You reach it by its own URL, `http://seat-selection-pr-42.demo.localhost:7080/`, or inside the environment by its own Service, `http://seat-selection-pr-42.apps`, until a [route](route.md) sends it calls made to `http://seat-selection`.
- Its revisions, its history and its resources are its own: a `provision` database is one per instance, and its `dns` gives it a host of its own.
- The first deploy names the component of the instance, and the instance keeps it. A deploy that names another component is refused (`409`), and so is an instance named like another component: its Service would answer for it.

`get`, `signals`, `rollback` and `remove` take the instance as an argument: `seat-selection-pr-42` with `--environment`, or `seat-selection-pr-42@demo` alone, the name `list` prints in its `WORKLOAD` column. The default instance is named after its component, so `seat-selection` stays `seat-selection`:

```bash
platform workload get seat-selection-pr-42@demo
```

`history --component` lists every instance of the component, and `history --instance` lists only one:

```bash
platform workload history \
  --environment demo \
  --component seat-selection

platform workload remove seat-selection-pr-42 \
  --environment demo \
  --wait
```

``` { .text .output title="output" }
WORKLOAD                   REVISION  ACTION  VERSION                  STATUS     BY               CREATED
seat-selection@demo        1         deploy  0.1.0-seat-pick.b5f9569  Succeeded  dev@example.com  2026-10-12T19:02:42Z
…
seat-selection@demo        6         deploy  0.1.0-seat-pick.b5f9569  Succeeded  dev@example.com  2026-10-12T19:04:49Z
seat-selection-pr-42@demo  1         deploy  0.1.0-farewell.910ace9   Succeeded  dev@example.com  2026-10-12T19:06:32Z
✓ seat-selection-pr-42@demo revision 2: removed from demo
```

In the plan of the environment, an extra instance is a key with `component:`:

```yaml
environment: demo
workloads:
  seat-selection:
    branch: feat/seat-pick
    replicas: 2
  seat-selection-pr-42:
    component: seat-selection
    branch: feat/farewell
```

`platform catalog component get seat-selection` lists it in `running in` as `seat-selection-pr-42@demo`. The default instance still shows by its environment alone.
