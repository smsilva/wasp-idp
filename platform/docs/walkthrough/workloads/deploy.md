# Deploy a version to an environment

A **Workload Instance** is a Workload Spec live in an environment: the Workload Instance is to the Workload Spec what a Helm release is to a chart. Each deploy is a new **revision** of the instance, and its short name is `<component>@<environment>`. The platform makes the resources of the Score, renders a Deployment and a Service in the namespace `apps` of the environment's vcluster and follows the rollout.

The version is the one [Build a branch](../builds/create.md) pushed to `ghcr-wasp-foundry`: the package of a public repo is public, so the vcluster pulls it without a credential. In the environment `demo` of [A second environment](../environments/second.md):

```bash
platform workload deploy \
  --component hello-api \
  --environment demo \
  --branch feat/greetings \
  --replicas 2 \
  --wait

platform workload list \
  --environment demo
```

``` { .text .output title="output" }
✓ hello-api@demo revision 1: 0.1.0-greetings.b5f9569 running · 2/2 replicas available
  url           http://hello-api.demo.localhost:7080/
  resource      db (postgres, provision): Ready
  resource      dns (dns, provision): Ready
  resource      route (route, provision): Ready
WORKLOAD        COMPONENT  VERSION                  STATUS     REPLICAS  REVISION  TRAFFIC  URL
hello-api@demo  hello-api  0.1.0-greetings.b5f9569  Available  2/2       1         —        http://hello-api.demo.localhost:7080/
```

- `--branch <branch>` deploys the newest version built from that branch; `--version <version>` picks one. The version is pinned in the revision: the instance does not follow the branch on its own.
- `--replicas` is an override of this environment: it goes into the revision, never into the spec. Without it, 1.
- Each `resource` line is a resource of the Score and the mode the binding policy gave it: `demo` is `shared`, so the `db` is a Postgres of its own (`provision`, [A database for a workload](resources/provision.md)). The `dns` and the `route` give the instance its URL ([Reach an instance from outside](public.md)).
- Without `--wait`, `deploy` returns at once with the revision number; `workload get` follows it.
- Deploying needs access to the environment (owner, a team it is shared with, or `platform-admins`) **and** membership in the component's owner team (or `platform-admins`). Reading needs access to the environment only.
- Without `--environment`, `workload list` shows the workloads of every environment you can use, with an `ENVIRONMENT` column; `--component hello-api` keeps the instances of one component.

The URL answers from your machine, with no `port-forward`:

```bash
platform workload get hello-api \
  --environment demo

curl --include http://hello-api.demo.localhost:7080/
```

``` { .text .output title="output" }
hello-api@demo (Available)
  component     hello-api
  version       0.1.0-greetings.b5f9569
  image         ghcr.io/wasp-foundry/hello-api@sha256:334d43c28141f754b0ac482de390c51fb1b377cd166c24b5d69d1f7f37e4ba3c
  replicas      2/2
  revision      1
  traffic       —
  url           http://hello-api.demo.localhost:7080/
  internal url  http://hello-api.apps:80
  message       2/2 replicas ready
  resource      db (postgres, provision): Ready
  resource      dns (dns, provision): Ready
  resource      route (route, provision): Ready
HTTP/1.1 200 OK
Content-Type: application/json
Server: istio-envoy

{"app":"hello-api","message":"hello"}
```

The image is pinned by digest: a new push under the same tag does not change what runs. The `internal url` is the address the other workloads of the environment use.

!!! note
    The platform keeps two objects in `platform-system`: one `WorkloadRevision` per act (`demo.hello-api.1`, immutable) and the `WorkloadInstance` (`demo.hello-api`), the runtime view the `workload` provider refreshes every 30 s. Both belong to the `Environment`: deleting the environment deletes them. `kubectl --context k3d-platform-local --namespace platform-system get workloadrevisions,workloadinstances`.
