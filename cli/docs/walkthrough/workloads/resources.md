# A database for a workload

A version whose Score declares `db: {type: postgres}` gets a database in each environment it is deployed to. The **Forager** resolves the mode of each resource from the binding policy, and by default it is `provision`: a Postgres of its own in the vcluster of the environment. The Score never carries a credential:

```yaml
resources:
  db:
    type: postgres
containers:
  app:
    image: .
    command: ["sh", "-c"]
    args: ["until psql --command 'select current_database()'; do sleep 2; done; sleep infinity"]
    variables:
      PGHOST: ${resources.db.host}
      PGPORT: ${resources.db.port}
      PGDATABASE: ${resources.db.name}
      PGUSER: ${resources.db.username}
      PGPASSWORD: ${resources.db.password}
```

With a version `0.5.0` of `hello-api` with that Score, whose app is the `psql` client of the public image `postgres:17-alpine` (written by `kubectl` as in [The spec of a version](spec.md)):

```bash
platform workload deploy \
  --component hello-api \
  --environment demo \
  --version 0.5.0 \
  --wait

platform workload get \
  --component hello-api \
  --environment demo
```

``` { .text .output title="output" }
✓ hello-api@demo revision 8: 0.5.0 running · 1/1 replicas available
hello-api@demo (Available)
  component     hello-api
  version       0.5.0
  image         docker.io/library/postgres@sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24
  replicas      1/1
  revision      8
  url           —
  message       1/1 replicas ready
  resource      db (postgres, provision): Ready
```

The app connects with the outputs and nothing else:

```bash
kubectl --kubeconfig ~/.config/platform/environments/demo.kubeconfig \
  --namespace apps \
  logs deployment/hello-api
```

``` { .text .output title="output" }
 current_database
------------------
 app
(1 row)
```

- While the database starts, the revision waits as `ResourcesPending`, and `--wait` keeps following it.
- `PGHOST` is `hello-api-db-<hash>.resources`, a namespace of the vcluster apart from the workloads, and `PGPASSWORD` is a `secretKeyRef` to the Secret of the same name in the namespace `apps`: the password is not in the Deployment.
- The next deploy reuses the same database. `workload remove` deletes it, and its data with it.
- The Score has no `id` for `db`, so the catalog gets the Resource `hello-api-db`, owned by the component's team: `platform catalog resource get hello-api-db`.

!!! note
    The Forager keeps one `ResourceRequest` per resource and environment in `platform-system` (`demo.hello-api.db`), with the mode in `spec` and the outputs in `status`. The platform default policy is the `BindingPolicy` `platform-default`. `kubectl --context k3d-platform-local --namespace platform-system get resourcerequests,bindingpolicies`. The whole flow, drawn: [The Forager](../../reference/forager.md).
