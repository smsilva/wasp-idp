# A database for a workload

A version whose Score declares `db: {type: postgres}` gets a database in each environment it is deployed to. The **Forager** resolves the mode of each resource from the binding policy, and by default it is `provision`: a Postgres of its own in the vcluster of the environment. The Score never carries a credential:

```yaml
resources:
  db:
    type: postgres
containers:
  app:
    image: .
    variables:
      DATABASE_HOST: ${resources.db.host}
      DATABASE_NAME: ${resources.db.name}
      DATABASE_USER: ${resources.db.username}
      DATABASE_PASSWORD: ${resources.db.password}
```

With a version `0.5.0` of `hello-api` with that Score (written by `kubectl` as in step 21.2):

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
  image         ghcr.io/stefanprodan/podinfo@sha256:862ca45e61b32392f7941a1bdfdbe5ff8b6899070135f1bdca1c287d0057fc94
  replicas      1/1
  revision      8
  url           http://hello-api.apps:80
  message       1/1 replicas ready
  resource      db (postgres, provision): Ready
```

- While the database starts, the revision waits as `ResourcesPending`, and `--wait` keeps following it.
- `DATABASE_HOST` is `hello-api-db-<hash>.resources`, a namespace of the vcluster apart from the workloads, and `DATABASE_PASSWORD` is a `secretKeyRef` to the Secret of the same name in the namespace `apps`: the password is not in the Deployment.
- The next deploy reuses the same database. `workload remove` deletes it, and its data with it.
- The Score has no `id` for `db`, so the catalog gets the Resource `hello-api-db`, owned by the component's team: `platform catalog resource get hello-api-db`.

!!! note
    The Forager keeps one `ResourceRequest` per resource and environment in `platform-system` (`demo.hello-api.db`), with the mode in `spec` and the outputs in `status`. The platform default policy is the `BindingPolicy` `platform-default`. `kubectl --context k3d-platform-local --namespace platform-system get resourcerequests,bindingpolicies`.
