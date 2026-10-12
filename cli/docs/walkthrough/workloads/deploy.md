# Deploy a version to an environment

A **Workload Instance** is a Workload Spec live in an environment: the Workload Instance is to the Workload Spec what a Helm release is to a chart. Each deploy is a new **revision** of the instance, and its short name is `<component>@<environment>`. The platform renders a Deployment and a Service from the Score in the namespace `apps` of the environment's vcluster and follows the rollout.

The image must be one the vcluster can pull without credentials. This step starts small: a version `0.3.0` whose Score has no resources, with the public image `ghcr.io/stefanprodan/podinfo` (written by `kubectl` as the build writes it, like in [The spec of a version](spec.md)). The database, the DNS name and the route of the `hello-api` of [Create a component](../components/create.md) come in [A database for a workload](resources.md) and [Reach an instance from outside](public.md); deploying the `hello-api` its build produced is #360.

In the environment `demo` of [A second environment](../environments/second.md):

```bash
platform workload deploy \
  --component hello-api \
  --environment demo \
  --version 0.3.0 \
  --replicas 2 \
  --wait

platform workload list \
  --environment demo
```

``` { .text .output title="output" }
✓ hello-api@demo revision 1: 0.3.0 running · 2/2 replicas available
WORKLOAD        COMPONENT  VERSION  STATUS     REPLICAS  REVISION  TRAFFIC  URL
hello-api@demo  hello-api  0.3.0    Available  2/2       1         —        http://hello-api.apps:80
```

- `--branch <branch>` deploys the newest version built from that branch instead of `--version`. The version is pinned in the revision: the instance does not follow the branch on its own.
- `--replicas` is an override of this environment: it goes into the revision, never into the spec. Without it, 1.
- Without `--wait`, `deploy` returns at once with the revision number; `workload get` follows it.
- Deploying needs access to the environment (owner, a team it is shared with, or `platform-admins`) **and** membership in the component's owner team (or `platform-admins`). Reading needs access to the environment only.

```bash
platform workload get \
  --component hello-api \
  --environment demo
```

``` { .text .output title="output" }
hello-api@demo (Available)
  component     hello-api
  version       0.3.0
  image         ghcr.io/stefanprodan/podinfo@sha256:862ca45e61b32392f7941a1bdfdbe5ff8b6899070135f1bdca1c287d0057fc94
  replicas      2/2
  revision      1
  url           http://hello-api.apps:80
  message       2/2 replicas ready
```

The URL is the address **inside the vcluster**: a Score without a `route` is not reached from outside ([Reach an instance from outside](public.md)). To reach the instance from your machine, use the kubeconfig that `environment get demo` wrote in [A second environment](../environments/second.md):

```bash
kubectl --kubeconfig ~/.config/platform/environments/demo.kubeconfig \
  --namespace apps \
  port-forward service/hello-api 8080:80
```

!!! note
    The platform keeps two objects in `platform-system`: one `WorkloadRevision` per act (`demo.hello-api.1`, immutable) and the `WorkloadInstance` (`demo.hello-api`), the runtime view the `workload` provider refreshes every 30 s. Both belong to the `Environment`: deleting the environment deletes them. `kubectl --context k3d-platform-local --namespace platform-system get workloadrevisions,workloadinstances`.
