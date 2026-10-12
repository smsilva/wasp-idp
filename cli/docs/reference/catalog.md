# Catalog

Domains, systems and shared resources that the platform stores (ADR 0023). The `--owner` is always a team that already exists ([Teams](teams.md)). Components live in their repo's `catalog-info.yaml`: the platform creates the repo and keeps an index ([Components](#components)). APIs are not in the platform catalog yet.

| Command | What it does |
|---|---|
| `platform catalog domain create <name> --owner <team> [--parent <domain>]` | creates a domain or, with `--parent`, a subdomain |
| `platform catalog system create <name> --domain <domain> --owner <team>` | creates a system |
| `platform catalog resource create <name> --type <role> --system <system> --owner <team>` | creates a shared resource; `--type` is the role (`database`, `topic`, `queue`, `bucket`), never the cloud service |
| `platform catalog list [--kind domain\|system\|resource] [--owner <team>]` | KIND, NAME, PARENT, OWNER |
| `platform catalog <kind> list\|get\|delete <name>` | per kind; `get` shows the dependents |

| Action | Who |
|---|---|
| create or delete a domain | `platform-admins` |
| create a system or a resource | any user |
| delete a system or a resource | whoever created it, or `platform-admins` |

An entity with dependents is not deleted: the API answers `409` naming them, so deleting goes in the reverse order.

## Components

```bash
platform catalog component create <name> --system <system> \
  [--owner <team>] [--type service|website|library | --template <template>] \
  [--param key=value]... [--description <text>] [--scm <connection>] \
  [--visibility public|private] [--prd <file>|-] [--wait] [--timeout <seconds>]
platform catalog component list [--system <system>] [--owner <team>]
platform catalog component get <name>
platform catalog component clone <name> [--directory <dir>] [--https]
```

`create` creates the repo on the org of the SCM connection from a template ([Templates](templates.md)), pushes the rendered content as a single first commit and registers the component (`lifecycle: experimental`). Any authenticated user creates; the creation steps are visible to whoever requested it and to `platform-admins`.

| Option | Default |
|---|---|
| `--owner` | your team, when you have exactly one; otherwise required |
| `--type` / `--template` | the default template of `service` |
| `--scm` | the default connection (`409` without one) |
| `--visibility` | the connection's `defaultVisibility` (`public`) |
| `--prd` | the template's `docs/prd.md` skeleton; the journal keeps only the hash of the text (at most 64 KiB) |

`list` shows NAME, SYSTEM, OWNER, LIFECYCLE and TEMPLATE. `get` shows the component and a `running in` line: the environments where a Workload Instance of it runs, with version and status ([Workloads](workloads.md#workload-instances)), only those you can use (JSON: `runningIn`). While the component is not in the index yet, `get` shows the creation steps.

`clone` runs `git clone` of the component's repo with your own Git credentials, printing the command first and exiting with the code of `git`. The URL is SSH (`git@github.com:<org>/<repo>.git`) unless `--https` is given or `~/.config/platform/config.yaml` has `git_protocol: https`; `--https` wins over the config. A component not in the index is refused before `git` runs ([Clone the component](../walkthrough/components/clone.md)).

| Step | Fails with |
|---|---|
| `Validated` | `ConnectionNotFound`, `ConnectionNotReady` |
| `Rendered` | `StepFailed` (fetch or render of the template) |
| `RepoCreated` | `RepoAlreadyExists`: a repo with that name that this request did not create; it is never touched. `RepoGone`: created, then deleted outside the platform |
| `Pushed` | a GitHub failure (below) |
| `Protected` | never fails the creation: `ProtectionUnavailable` is a warning, `main` stays unprotected (GitHub Free has no branch protection for private repos) |
| `Registered` | `ComponentExists`: the index has that name for another repo |

`Protected` makes `main` change only through a pull request, with no approval required: the org may have a single member, who cannot approve their own PR (ADR 0017). On a private repo of a GitHub Free org, `--wait` ends with the warning:

``` { .text .output title="output" }
⚠ main of wasp-foundry/hello-api is not protected: GitHub answered 403: PUT /repos/wasp-foundry/hello-api/branches/main/protection: Upgrade to GitHub Pro or make this repository public to enable this feature.
```

A GitHub failure in any step is one of:

| Reason | Meaning | Retried |
|---|---|---|
| `RateLimited` | GitHub's rate limit | after the `retry-after` or `x-ratelimit-reset` GitHub sends |
| `GitHubUnavailable` | GitHub answered 5xx, or could not be reached | with backoff, from 30 s doubling up to 10 min |
| `GitHubRejected` | any other 4xx, with GitHub's message | no: the creation stops |
| `StepFailed` | the cluster unavailable, or an unexpected error | with backoff |

The connection reasons are retried with backoff too, but `--wait` stops at them, at `GitHubRejected` and at the step reasons above; it keeps waiting on the others. A creation is removed 24 h after it ends `Ready`, or after it stops on `RepoAlreadyExists`, `RepoGone`, `ComponentExists` or `GitHubRejected`: then `component get` shows only the index, and a stopped name is free to request again. The index is a read mirror of the repo's `catalog-info.yaml`: no command changes or deletes a component, and deleting the repo is done on GitHub.

## Import from Backstage

```bash
platform catalog import <path>... \
  [--repo <url> --ref <ref>] \
  [--dry-run] \
  [--yes]
```

Imports Backstage files (a file or a folder, recursive `*.yaml`/`*.yml`). The Platform API computes the plan and nothing is written before the confirmation; `--dry-run` shows only the plan, `--yes` applies without asking.

| Action | Meaning |
|---|---|
| `create` | does not exist on the platform |
| `update` | exists and changes; the detail shows `field: before → after` |
| `unchanged` | exists and is identical |
| `skip` | not imported: Component and API arrive through discovery (#205), User stays in Keycloak, files inside a template's content, the `steps` of a Backstage template |
| `forbidden` | no permission |
| `error` | missing field or broken reference; the detail names the field and the file |

- A `Group` becomes a team (`platform-admins` only; members are not imported) and enters the plan before the other entities.
- With any `forbidden` or `error`, nothing is applied.
- The import never deletes. A field missing from the file is removed from the entity.
- If the catalog changes between the plan and the confirmation, the API refuses and the CLI shows the new plan.
- Templates (`kind: Template`) need `--repo` and `--ref`; without them they become `error` and the rest of the plan goes on.
