# Workloads

```bash
platform workload spec validate [--file <app-spec.yaml>]
platform workload spec get --component <component> [--version <version> | --branch <branch>]
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
