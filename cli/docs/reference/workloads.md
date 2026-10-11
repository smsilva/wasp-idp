# Workloads

```bash
platform workload spec validate [--file <app-spec.yaml>]
platform workload spec get --component <component> [--version <version> | --branch <branch>]
platform workload deploy --component <component> --environment <environment> (--version <version> | --branch <branch>) [--replicas <n>] [--wait] [--timeout <seconds>]
platform workload list --environment <environment>
platform workload get --component <component> --environment <environment>
platform workload history --environment <environment> [--component <component>]
platform workload rollback --component <component> --environment <environment> [--revision <n>] [--wait] [--timeout <seconds>]
platform workload remove --component <component> --environment <environment> [--wait] [--timeout <seconds>]
platform workload apply --file <plan.yaml> [--dry-run] [--prune] [--wait] [--timeout <seconds>]
```

A **Workload Spec** is the `app-spec.yaml` ([Score](https://score.dev), `score.dev/v1b1`) of a version, immutable, kept by the build in the version index (`spec.appSpec` of the `Version`). `spec validate` is open to any authenticated user. `spec get` is for members of the component's owner team and `platform-admins`: a Score may carry plain values from a private repo.

## spec validate

Runs the check of the build's `SpecValidated` step (see [Builds](builds.md#steps)) on a local file: the Score schema, the resource types the platform provisions (`postgres`, `dns`, `route`) and each `resources.<name>.id` against the Resources of the catalog. Prints `✓ <file> valid · <resources>`, or one `field: reason` line per error and exits with `1`. With `--output json`: `{"valid", "errors": [{"field", "reason"}], "resources": [{"name", "type"}]}`, and still exit code `1` when invalid. The file may have at most 64 KiB.

## spec get

Prints the spec of a version as YAML, preceded by a comment line `# <component> <version> · <branch> @ <commit>`: the output is a valid `app-spec.yaml`. The top-level keys follow the order of a Score; nested keys come sorted, as the kube API stores them. With `--output json`: `component`, `version`, `commit`, `branch`, `image`, `digest`, `createdAt` and `appSpec`.

| Option | Version |
|---|---|
| none | the newest version of the component (by creation time) |
| `--version <version>` | that version |
| `--branch <branch>` | the newest version built from that branch |

| Refusal | Code |
|---|---|
| `--version` and `--branch` together | refused by the CLI (`422` from the API) |
| you are neither in the component's owner team nor in `platform-admins` | `403` |
| the component is not in the index, or has no such version | `404` |
| the version was indexed before the index kept the spec (`SpecNotIndexed`) | `409` |

## Workload Instances

**The Workload Instance is to the Workload Spec what a Helm Release is to a Chart.** It is a Workload Spec live in an environment, kept by the platform, and the source of the runtime data. Each act on it (a deploy) is a **revision**, immutable, with its result. The short name of an instance is `<instance>@<environment>`; in phase 1 the instance is named after the component, so `--component` picks it and a component has at most one instance per environment.

Where the analogy breaks: the chart carries templates, while the Score declares what the app needs and the platform renders it; a Helm release lives in the target cluster, while the instance lives in the control plane, because the vcluster credential never leaves the platform; and the status of a release is the install's, while the instance follows the runtime health continuously.

The `workload` provider renders a Deployment and a Service named after the instance in the namespace `apps` of the environment's vcluster, labelled `app.kubernetes.io/name: <component>` and `app.kubernetes.io/instance: <instance>` (the Service selects both), applies them with server-side apply and follows the rollout. `image: .` in the Score becomes the image of the version by digest.

| Access | Who |
|---|---|
| `deploy`, `rollback`, `remove`, `apply` | access to the environment (owner, a team it is shared with, `platform-admins`) **and** the component's owner team or `platform-admins` |
| `list`, `get`, `history` | access to the environment |

Phase 1 accepts a Score with `containers` (`image`, `command`, `args`, `variables`, `resources`, `livenessProbe`/`readinessProbe` with `httpGet`) and `service.ports`. Placeholders: `${metadata.<key>}` and `${resources.<name>.<key>}` (see [Resources](#resources)); any other field is `UnsupportedSpec`. The image must be pullable by the vcluster without credentials.

## deploy

Writes revision `<n>` (the newest plus one) of the instance and prints `<instance>@<environment> revision <n>: deploying <version> …`. `--branch` is resolved by the API to the newest version built from that branch, and the revision keeps that version: the instance does not follow the branch. `--replicas` (0 to 20, default 1) is an override of the environment, kept in the revision. With `--wait`, follows the revision until the provider closes it: `✓ <instance>@<environment> revision <n>: <version> running · <ready>/<desired> replicas available`, or `✗ … revision <n>: <reason>: <message>` and exit code `1`.

| Revision status | Meaning |
|---|---|
| `Pending` | open: being applied, or rolling out |
| `EnvironmentNotReady` | open: waits for the environment to be `ready` |
| `ResourcesPending` | open: waits for the Forager to resolve and provision the resources of the Score |
| `Succeeded` | the rollout finished; the instance runs this revision |
| `SpecNotIndexed` | the version has no Workload Spec in the index |
| `ResourcesNotSupported` | a resource has no provisioner in the environment's policy (`dns`, `route`, or a `class` nobody offers) |
| `ResourceModeChanged` | a resource already exists in another mode; remove the workload and deploy again to change it |
| `ResourcesFailed` | the provisioner of a resource failed |
| `UnsupportedSpec` | the Score uses a field outside phase 1 |
| `ApplyFailed` | the vcluster refused the objects, or could not be reached |
| `RolloutFailed` | no progress for 120 s (`progressDeadlineSeconds`): an image that cannot be pulled, a crash loop |
| `Superseded` | a newer revision of the same instance came before this one finished |

A revision that does not succeed leaves the running revision as it was.

| Refusal | Code |
|---|---|
| neither or both of `--version` and `--branch` | refused by the CLI (`422` from the API) |
| no access to the environment, or outside the component's owner team | `403` |
| unknown environment or component, or no such version in the index | `404` |
| `SpecNotIndexed` | `409` |
| another deploy of the same instance took the revision number | `409`: run it again |

## Resources

A resource of the Score (`resources.db: {type: postgres}`) becomes a **`ResourceRequest`** per environment, `<environment>.<instance>.<resource>`, kept by the **Forager**. For each deploy, the Forager resolves the mode of each resource in the **binding policy** of the environment, then in the platform default (`BindingPolicy` `platform-default`), and the first item that matches the type, the `class` and the `id` of the resource wins. A `class` in the Score (`resources.db.class`) needs an item with that class: a class nobody offers ends as `ResourcesNotSupported`, never as a resource of another kind.

| Mode | What the platform does | Status |
|---|---|---|
| `provision` | a dedicated resource in the environment: for `postgres`, a Postgres in the namespace `resources` of the vcluster, named `<instance>-<resource>-<hash>`, without a volume; its password is a Secret of the same name in `apps` | available, the platform default |
| `compose` | something inside a shared resource: a database on a shared Postgres | #305 |
| `bind` | the credentials of a resource that already exists | #306 |

The revision waits as `ResourcesPending` until every resource is ready, then the outputs fill the placeholders: `${resources.db.host}`, `port`, `name`, `database`, `username`. A secret output (`password`) is accepted only as the whole value of a variable and becomes a `secretKeyRef` to a Secret in the vcluster: the password never appears in the Deployment, in the revision or in the API. Inside another string, in `command` or in `args`, it is `UnsupportedSpec`.

The mode of a resource never changes in place: a deploy that would resolve it to another mode ends as `ResourceModeChanged`. `remove` and a new `deploy` change it. A resource without `id` also gets a Resource in the catalog, `<component>-<resource>`, with the component's owner and System; it stays when the workload goes.

## list and get

`list` prints one line per instance: `WORKLOAD`, `VERSION`, `STATUS`, `REPLICAS` (ready/desired), `REVISION` (the one running) and `URL`. An instance whose first revision is still open shows as `Pending`; one whose only revision failed is not listed. `get` shows one instance, and a `newest` line when the newest revision is not the one running. Instance status: `Available`, `Progressing` (a rollout under way) or `Degraded` (fewer ready replicas than desired after the rollout, or a failed rollout), refreshed every 30 s. The URL is the address inside the vcluster (`http://<instance>.apps:<port>`); from your machine, `kubectl port-forward` with the environment's kubeconfig. `get` also prints one `resource` line per resource of the running revision: `<name> (<type>, <mode>): <status>`. With `--output json`, `latestRevision` carries the newest revision and `resources` the list of `{name, type, mode, status}`.

## history

The revisions of the environment, oldest first, optionally of one component: `WORKLOAD`, `REVISION`, `ACTION`, `VERSION`, `STATUS`, `BY` (who asked) and `CREATED`. Revisions stay until the environment is deleted.

## rollback

Writes a new revision (`action: rollback`, `rollbackOf: <n>`) with the version and the overrides (`--replicas`) of revision `<n>` of the same instance: the history keeps moving forward, as `helm rollback` does. Without `--revision`, the newest revision that succeeded before the one running. `--wait` as in `deploy`.

| Refusal | Code |
|---|---|
| no earlier revision that succeeded (default `--revision`) | refused by the CLI |
| revision `<n>` does not exist for the instance | `404` |
| revision `<n>` is a remove, or did not succeed | `409` |

## remove

Writes a revision `action: remove`: the provider deletes the Deployment and the Service from the vcluster, the `ResourceRequest`s of the instance (the Forager undoes each resource: a provisioned Postgres goes with its data), then the `WorkloadInstance`. The revisions stay until the environment is deleted, so `history` still shows them and `rollback` cannot target the remove itself. A later `deploy` starts the instance again, with the next revision number. With `--wait`: `✓ <instance>@<environment> revision <n>: removed from <environment>`. `404` when the environment has no such workload.

## apply

Applies the **plan** of an environment, the set of its workloads, as a helmfile does for Helm releases. There is no plan object in the platform: the plan is the sum of the instances.

```yaml
environment: demo
workloads:
  productpage:
    version: 1.4.0
  reviews:
    branch: feat/v3
    replicas: 2
```

The environment comes from the file. Each key under `workloads` is an instance; in phase 1 it is named after its component, and a `component:` that differs from the key is refused (`422`, more instances per component is #294). Each entry takes `version` or `branch` and optionally `replicas` (1 by default). An empty plan is written `workloads: {}`.

`POST /v1/environments/{environment}/workloads:apply` (`{"workloads": ..., "dryRun": true, "prune": false}`) diffs the plan against the newest revision of each instance:

| Action | When |
|---|---|
| `add` | the instance does not run (never deployed, removed, or its first deploy failed) |
| `change` | the version or the replicas differ, or the newest revision failed: applying tries it again |
| `unchanged` | same version and replicas, and the newest revision succeeded or is still open |
| `remove` | with `--prune`, an instance that runs and the plan leaves out |

Each `add` and `change` is a `deploy` revision, each `remove` a remove revision, as `deploy` and `remove` write them. Every instance is authorized and resolved (version in the index, branch to its newest version, `SpecNotIndexed`) before the first write: one refusal (`403`, `404`, `409`, `422`) applies nothing. The writes are not transactional: a revision number taken by a concurrent request stops the apply with `409` and the number of revisions applied before it; applying again converges.

The output lists each workload with its action, `FROM`/`TO` as `<version> ×<replicas>` and the revision written, then `<environment>: N to add, N to change, N to remove`. `--dry-run` writes nothing. `--wait` follows every revision written, prints one line per revision as `deploy` and `remove` do, and exits `1` when one does not succeed; `--timeout` applies to each revision.
