# Builds

```bash
platform build create --component <component> --branch <branch> \
  [--version <major.minor.patch[-pre-release]>] [--wait] [--timeout <seconds>]
platform build list --component <component>
platform build get <build>
```

`create` turns a branch of a component into a version. The platform dispatches the repo's `.github/workflows/platform-build.yaml` on GitHub Actions with the App of the org's SCM connection, follows the run, reads its `platform-build` artifact, checks `app-spec.yaml` at the built commit and registers the version in the index. The App, not you, dispatches and reads the repo, so GitHub does not decide who builds: only members of the component's owner team and `platform-admins` create a build. `list` and `get` are open to any authenticated user, like the component index.

`list` reads the version index (VERSION, BRANCH, CREATED, newest first): only versions whose `app-spec.yaml` passed. `get` shows a build and its steps; a build is removed 24 h after it ends, the version stays.

## The contract with the CI

Any workflow that keeps it works, with or without Commitizen. The `python-service` template brings one.

| Part | Contract |
|---|---|
| File | `.github/workflows/platform-build.yaml`, on the default branch (GitHub dispatches only workflows it finds there) |
| Inputs | `workflow_dispatch` with `request-id` (required) and `version` (optional) |
| Run name | `run-name: platform-build ${{ inputs.request-id }}`: how the platform finds the run it dispatched |
| Version | `version` when given; otherwise `cz bump --get-next` (no tag: `0.1.0`; no commit to bump: the tagged version), with `-<slug>.<sha7>` outside `main`. The slug is the branch without its `<type>/` prefix, lowercase, `[^a-z0-9]` as `-`, at most 20 characters |
| Image | `ghcr.io/<repo>:<version>`, OCI manifest (buildx, `oci-mediatypes=true`) with the `org.opencontainers.image.source`, `.revision`, `.version` and `me.silvios.wasp.request-id` annotations |
| Output | an artifact `platform-build` with `platform-build.json`: `version`, `image` (no tag), `digest`, `commit`, `branch`, `requestId` |

The CI holds no platform credential: the platform pulls the run and the artifact.

## Refusals before GitHub

| Refusal | Code |
|---|---|
| the component is not in the index, or has no repo | `422` |
| you are neither in the component's owner team nor in `platform-admins` | `403` |
| `--version` or `--branch` malformed | `422` |
| `--version` already in the index (the CI would push the tag again) | `409` |
| no SCM connection for the repo's org, or it is not `ready` | `409` |

## Steps

| Step | Fails with |
|---|---|
| `Dispatched` | `WorkflowNotFound`: no `platform-build.yaml` on the default branch. `BranchNotFound`. `ContractViolation`: the workflow refused the inputs (no `workflow_dispatch`, or no `request-id`/`version` input) |
| `Running` | `ContractViolation`: no run named `platform-build <request-id>` 10 minutes after the dispatch. While the run is queued or in progress, `Ready` is `False` with reason `Building` |
| `Succeeded` | `BuildFailed`: the run did not end in success (the message has the run URL). `ContractViolation`: no `platform-build` artifact, or a `platform-build.json` that breaks the contract (missing fields, another `requestId` or branch, a version other than `--version`) |
| `SpecValidated` | `InvalidSpec`, with one error per field: `app-spec.yaml` missing at the commit, not Score (`score.dev/v1b1`, schema vendored in `platform/libs/score`), a resource type the platform does not provision (`postgres`, `dns`, `route`), or a `resources.<name>.id` that is not a Resource in the catalog |
| `Ready` | `VersionConflict`: the version is in the index from another commit; the entry is left untouched. On success, the version keeps the validated spec ([Workloads](workloads.md)) |

GitHub and cluster failures (`RateLimited`, `GitHubUnavailable`, `GitHubRejected`, `StepFailed`) and the connection reasons (`ConnectionNotFound`, `ConnectionNotReady`, `CredentialMissing`) behave as for [components](catalog.md#components). `--wait` stops at every reason above except `Building` and the retried ones; it waits 1200 s by default.

On `InvalidSpec` the image is in the registry, but the version does not exist for the platform. `platform workload spec validate` runs the same check on a local file, before the build.
