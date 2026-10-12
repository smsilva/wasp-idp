# Workloads

```bash
platform workload spec validate [--file <app-spec.yaml>]
platform workload spec get --component <component> [--version <version> | --branch <branch>]
platform workload deploy --component <component> [--instance <instance>] --environment <environment> (--version <version> | --branch <branch>) [--replicas <n>] [--resource-class <resource>=<class> ...] [--wait] [--timeout <seconds>]
platform workload list --environment <environment>
platform workload get (--component <component> | --instance <instance>) --environment <environment>
platform workload history --environment <environment> [--component <component> | --instance <instance>]
platform workload rollback (--component <component> | --instance <instance>) --environment <environment> [--revision <n>] [--wait] [--timeout <seconds>]
platform workload remove (--component <component> | --instance <instance>) --environment <environment> [--wait] [--timeout <seconds>]
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

**The Workload Instance is to the Workload Spec what a Helm Release is to a Chart.** It is a Workload Spec live in an environment, kept by the platform, and the source of the runtime data. Each act on it (a deploy) is a **revision**, immutable, with its result. The short name of an instance is `<instance>@<environment>`. An instance is named after its component by default; a component may have more instances in the same environment (see [Instances](#instances)).

Where the analogy breaks: the chart carries templates, while the Score declares what the app needs and the platform renders it; a Helm release lives in the target cluster, while the instance lives in the control plane, because the vcluster credential never leaves the platform; and the status of a release is the install's, while the instance follows the runtime health continuously.

The `workload` provider renders a Deployment and a Service named after the instance in the namespace `apps` of the environment's vcluster, labelled `app.kubernetes.io/name: <component>` and `app.kubernetes.io/instance: <instance>` (the Service selects both), applies them with server-side apply and follows the rollout. `image: .` in the Score becomes the image of the version by digest.

| Access | Who |
|---|---|
| `deploy`, `rollback`, `remove`, `apply`, `route` | access to the environment (owner, a team it is shared with, `platform-admins`) **and** the component's owner team or `platform-admins` |
| `list`, `get`, `history` | access to the environment |

Phase 1 accepts a Score with `containers` (`image`, `command`, `args`, `variables`, `resources`, `livenessProbe`/`readinessProbe` with `httpGet`) and `service.ports`. Placeholders: `${metadata.<key>}` and `${resources.<name>.<key>}` (see [Resources](#resources)); any other field is `UnsupportedSpec`. The image must be pullable by the vcluster without credentials.

## Instances

`deploy --instance <instance>` runs another instance of the component next to the default one, as the shared sandbox of a pull request does: the stable version and the version of a branch side by side, against the same services. Each instance has a Deployment and a Service of its own, `<instance>`; the Service of the component selects `app.kubernetes.io/instance: <component>` too, so an extra instance gets no traffic from it until a [route](#route) sends it some. Its resources are its own as well: a `provision` resource is a database per instance (`<instance>-<resource>-<hash>`).

An instance runs one component for as long as its history lives: the first deploy names it, and a deploy or a plan that names another component is refused (`409`). An extra instance cannot take the name of another component of the catalog (`409`): its Service would answer for that component (`http://<component>`) in the environment.

`get`, `rollback` and `remove` take `--component` or `--instance`. With `--component`, the CLI acts on the default instance, the one named after the component; when the component runs any extra instance in the environment it stops with `<component> has N instances in <environment>: …; give --instance`, so `--component` never lands on a sandbox unasked. `deploy` always sends the component: deploying another component to an existing instance is a 409. `history --component` lists the revisions of every instance of the component; `--instance`, only those of one.

## deploy

Writes revision `<n>` (the newest plus one) of the instance, `--instance` or by default the component name, and prints `<instance>@<environment> revision <n>: deploying <version> …`. `--branch` is resolved by the API to the newest version built from that branch, and the revision keeps that version: the instance does not follow the branch. `--replicas` (0 to 20, default 1) is an override of the environment, kept in the revision. `--resource-class db=restored` (repeatable) is an override too: the Forager resolves the resource `db` with that class, ahead of a `class` in the Score. A resource the version does not have is refused (`422`). With `--wait`, follows the revision until the provider closes it: `✓ <instance>@<environment> revision <n>: <version> running · <ready>/<desired> replicas available`, or `✗ … revision <n>: <reason>: <message>` and exit code `1`.

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
| the instance runs another component, or `--instance` is the name of another component | `409`: pick another `--instance` |
| another deploy of the same instance took the revision number | `409`: run it again |

## Resources

A resource of the Score (`resources.db: {type: postgres}`) becomes a **`ResourceRequest`** per environment, `<environment>.<instance>.<resource>`, kept by the **Forager**. For each deploy, the Forager resolves the mode of each resource in the **binding policy** of the environment, then in the platform default (`BindingPolicy` `platform-default`), and the first item that matches the type, the `class` and the `id` of the resource wins. A `class` in the Score (`resources.db.class`) needs an item with that class: a class nobody offers ends as `ResourcesNotSupported`, never as a resource of another kind. How the Forager and the workload provider split a deploy, with diagrams: [The Forager](forager.md).

| Mode | What the platform does | Status |
|---|---|---|
| `provision` | a dedicated resource in the environment: for `postgres`, a Postgres in the namespace `resources` of the vcluster, named `<instance>-<resource>-<hash>`, without a volume; its password is a Secret of the same name in `apps` | available, the platform default |
| `compose` | something inside a shared resource: for `postgres`, a role and a database of their own in `shared-pg` | available, by the policy of the environment |
| `bind` | a resource that already exists: for `postgres`, the values of the policy item and the password of a bindable Secret, copied to `apps` | available, by a `class` in the policy of the environment |

The revision waits as `ResourcesPending` until every resource is ready, then the outputs fill the placeholders: `${resources.db.host}`, `port`, `name`, `database`, `username`. A secret output (`password`) is accepted only as the whole value of a variable and becomes a `secretKeyRef` to a Secret in the vcluster: the password never appears in the Deployment, in the revision or in the API. Inside another string, in `command` or in `args`, it is `UnsupportedSpec`.

The mode and the class of a resource never change in place: a deploy that would resolve it to another mode or ask for another class ends as `ResourceModeChanged`. `remove` and a new `deploy` change it. A resource without `id` also gets a Resource in the catalog, `<component>-<resource>`, with the component's owner and System; it stays when the workload goes.

## list and get

`list` prints one line per instance: `WORKLOAD`, `COMPONENT`, `VERSION`, `STATUS`, `REPLICAS` (ready/desired), `REVISION` (the one running), `TRAFFIC` and `URL`. `TRAFFIC` is what the [route](#route) of the component sends to the instance: `x-sandbox=pr-42` (a header), `baggage sandbox=pr-42`, `10%` (its weight), several joined by `, `; `default` on the main instance when it only takes what no rule matched; `—` without a route. An instance whose first revision is still open shows as `Pending`; one whose only revision failed is not listed. `get` shows one instance, and a `newest` line when the newest revision is not the one running. Instance status: `Available`, `Progressing` (a rollout under way) or `Degraded` (fewer ready replicas than desired after the rollout, or a failed rollout), refreshed every 30 s. The URL is the address inside the vcluster (`http://<instance>.apps:<port>`); from your machine, `kubectl port-forward` with the environment's kubeconfig. `get` also prints one `resource` line per resource of the running revision: `<name> (<type>, <mode>): <status>`, with `, class <class>` when the newest revision asks for one. With `--output json`, `latestRevision` carries the newest revision and `resources` the list of `{name, type, mode, status}`.

## route

Splits the calls made to a component's Service (`http://<component>`) among its instances in an environment. A route is one object per component and environment, a `WorkloadRoute` named `<environment>.<component>`, with an ordered list of rules; the `workload` provider turns it into a Gateway API `HTTPRoute` (GAMMA, `parentRef` on the Service `<component>`) in the namespace `apps` of the vcluster, which the environment's Istio applies. A call that no rule matches goes to the main instance, `<component>`.

| Option | Rule |
|---|---|
| `--header name=value --to <instance>` | calls with the header go to the instance |
| `--baggage key=value --to <instance>` | calls whose `baggage` header (OpenTelemetry Baggage) has the entry go to the instance; the services pass it on, so it holds down a chain of calls ([contract](../walkthrough/workloads/baggage.md)) |
| `--weight n --to <instance>` | `n`% of the calls that no header or baggage rule took go to the instance; the main instance takes the rest |
| `--clear` | removes the route |

The CLI reads the route (`GET /v1/environments/{environment}/workloads/routes/{component}`), changes one rule and writes the whole list back (`PUT`, `{"rules": [...]}`); `--clear` is a `DELETE`. A header or baggage rule replaces the one with the same match (header names are case-insensitive); a weight keeps the share of the other instances and gives the rest to the main one, and `--weight 0` takes the instance out. The write is last-write-wins: two people changing the route of the same component at the same time keep only the second one's rules.

Header names take letters, digits and `-`; values and baggage keys letters, digits, `.`, `_` and `-`. The route takes effect in about a second; `GET` shows its status: `Accepted`, `Pending` (the mesh has not looked at it yet), `InstancePending` (an instance with no Service yet), `MeshNotInstalled` (an environment created before the mesh: create it again), `ApplyFailed`, or the reason the mesh gave.

| Refusal | Code |
|---|---|
| `--to` an instance that does not run in the environment | `409` |
| `--to` an instance of another component | `409` |
| the main instance `<component>` does not run (the route attaches to its Service) | `409` |
| weights that do not add up to 100, a weights rule that is not the last, two rules with the same match | `422` |
| `remove` of an instance a rule sends traffic to, or of the main instance while the route exists | `409` |
| `apply --prune` that would remove one of those | `409`, before any write |

Only calls from pods in the namespace `apps` go through the mesh, and a header only travels down a chain of calls when each service passes it on. Traffic from outside the environment is not routed.

## history

The revisions of the environment, oldest first, optionally of one component (all its instances) or of one instance: `WORKLOAD`, `REVISION`, `ACTION`, `VERSION`, `STATUS`, `BY` (who asked) and `CREATED`. Revisions stay until the environment is deleted.

## rollback

Writes a new revision (`action: rollback`, `rollbackOf: <n>`) with the version and the overrides (`--replicas`, `--resource-class`) of revision `<n>` of the same instance: the history keeps moving forward, as `helm rollback` does. Without `--revision`, the newest revision that succeeded before the one running. `--wait` as in `deploy`.

| Refusal | Code |
|---|---|
| no earlier revision that succeeded (default `--revision`) | refused by the CLI |
| revision `<n>` does not exist for the instance | `404` |
| revision `<n>` is a remove, or did not succeed | `409` |

## remove

Writes a revision `action: remove`: the provider deletes the Deployment and the Service from the vcluster, the `ResourceRequest`s of the instance (the Forager undoes each resource: a provisioned Postgres goes with its data), then the `WorkloadInstance`. The revisions stay until the environment is deleted, so `history` still shows them and `rollback` cannot target the remove itself. A later `deploy` starts the instance again, with the next revision number. With `--wait`: `✓ <instance>@<environment> revision <n>: removed from <environment>`. `404` when the environment has no such workload; `409` while a [route](#route) sends traffic to it, or when it is the main instance of a route.

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
    resourceClasses:
      db: restored
```

The environment comes from the file. Each key under `workloads` is an instance of the component named like the key, or of the one `component:` names (an extra instance, see [Instances](#instances)); an instance that runs another component is refused (`409`). Each entry takes `version` or `branch`, optionally `replicas` (1 by default) and `resourceClasses` (resource to class, as `deploy --resource-class`: a resource the version does not have is refused with `422`). An empty plan is written `workloads: {}`.

`POST /v1/environments/{environment}/workloads:apply` (`{"workloads": ..., "dryRun": true, "prune": false}`) diffs the plan against the newest revision of each instance:

| Action | When |
|---|---|
| `add` | the instance does not run (never deployed, removed, or its first deploy failed) |
| `change` | the version, the replicas or the resource classes differ, or the newest revision failed: applying tries it again |
| `unchanged` | same version, replicas and resource classes, and the newest revision succeeded or is still open |
| `remove` | with `--prune`, an instance that runs and the plan leaves out |

Each `add` and `change` is a `deploy` revision, each `remove` a remove revision, as `deploy` and `remove` write them. Every instance is authorized and resolved (version in the index, branch to its newest version, `SpecNotIndexed`) before the first write: one refusal (`403`, `404`, `409`, `422`) applies nothing. The writes are not transactional: a revision number taken by a concurrent request stops the apply with `409` and the number of revisions applied before it; applying again converges.

The output lists each workload with its action, `FROM`/`TO` as `<version> ×<replicas>` (plus `<resource>=<class>` for each class) and the revision written, then `<environment>: N to add, N to change, N to remove`. `--dry-run` writes nothing. `--wait` follows every revision written, prints one line per revision as `deploy` and `remove` do, and exits `1` when one does not succeed; `--timeout` applies to each revision.
