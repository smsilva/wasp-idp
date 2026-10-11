# Workloads

```bash
platform workload spec validate [--file <app-spec.yaml>]
platform workload spec get --component <component> [--version <version> | --branch <branch>]
platform workload deploy --component <component> --environment <environment> (--version <version> | --branch <branch>) [--replicas <n>] [--wait] [--timeout <seconds>]
platform workload list --environment <environment>
platform workload get --component <component> --environment <environment>
platform workload history --environment <environment> [--component <component>]
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
| `deploy` | access to the environment (owner, a team it is shared with, `platform-admins`) **and** the component's owner team or `platform-admins` |
| `list`, `get`, `history` | access to the environment |

Phase 1 accepts a Score with `containers` (`image`, `command`, `args`, `variables`, `resources`, `livenessProbe`/`readinessProbe` with `httpGet`) and `service.ports`. The only placeholder resolved is `${metadata.<key>}`. Declared `resources` end as `ResourcesNotSupported` until the platform provisions them (#263), any other field as `UnsupportedSpec`. The image must be pullable by the vcluster without credentials.

## deploy

Writes revision `<n>` (the newest plus one) of the instance and prints `<instance>@<environment> revision <n>: deploying <version> …`. `--branch` is resolved by the API to the newest version built from that branch, and the revision keeps that version: the instance does not follow the branch. `--replicas` (0 to 20, default 1) is an override of the environment, kept in the revision. With `--wait`, follows the revision until the provider closes it: `✓ <instance>@<environment> revision <n>: <version> running · <ready>/<desired> replicas available`, or `✗ … revision <n>: <reason>: <message>` and exit code `1`.

| Revision status | Meaning |
|---|---|
| `Pending` | open: being applied, or rolling out |
| `EnvironmentNotReady` | open: waits for the environment to be `ready` |
| `Succeeded` | the rollout finished; the instance runs this revision |
| `SpecNotIndexed` | the version has no Workload Spec in the index |
| `ResourcesNotSupported` | the Score declares `resources` (#263) |
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

## list and get

`list` prints one line per instance: `WORKLOAD`, `VERSION`, `STATUS`, `REPLICAS` (ready/desired), `REVISION` (the one running) and `URL`. An instance whose first revision is still open shows as `Pending`; one whose only revision failed is not listed. `get` shows one instance, and a `newest` line when the newest revision is not the one running. Instance status: `Available`, `Progressing` (a rollout under way) or `Degraded` (fewer ready replicas than desired after the rollout, or a failed rollout), refreshed every 30 s. The URL is the address inside the vcluster (`http://<instance>.apps:<port>`); from your machine, `kubectl port-forward` with the environment's kubeconfig. With `--output json`, `latestRevision` carries the newest revision.

## history

The revisions of the environment, oldest first, optionally of one component: `WORKLOAD`, `REVISION`, `ACTION`, `VERSION`, `STATUS`, `BY` (who asked) and `CREATED`. Revisions stay until the environment is deleted.
