# Status

```bash
platform status [<capability>] [--verbose] [--output json]
```

Each capability of the platform, who implements it and whether it works. The Platform API computes it from the Deployments that implement each capability and from what operators configure (ADR 0039); the CLI only lays it out.

| Command | What it prints |
|---|---|
| `platform status` | one line per capability |
| `platform status <capability>` | that capability in full: its drivers, and its connections or accounts |
| `platform status --verbose` | every capability in full, then the summary |

The exit code is `1` when an installed capability is not `Active`; a capability with no provider installed is not a failure. With `--output json`, the same exit code.

## What each role sees

- **platform-users:** the capability and its status. Under a capability that is not `Active`: `ask a platform-admin to configure it`.
- **platform-admins:** also the providers, a short detail and, when something is missing, the command that fixes it (`fix`). In full: each driver with its version (the tag of its image), its replicas and its status, plus what the capability serves:
    - `scm`: each connection, with its vendor, org and status;
    - `registry`: each registry, with its vendor, address and status;
    - `cloud-account`: the base identity of each driver, and the accounts counted by vendor (never named: they belong to their owners; `platform cloud account list` shows the ones you can see).

## The capabilities

The subsystems of ADR 0034, in its order: `identity`, `catalog`, `environment`, `scm`, `registry`, `build`, `cloud-account`, `resources`, `workload`, then `observability` (ADR 0040: the Prometheus `platform init` installs, which `workload signals` reads). `depends on` comes from the same map.

A capability can have one **driver** per vendor: `scm` is served by `scm_github` today, and a Bitbucket driver would be one more line under the same capability. `environment` has `local_vcluster` and, after `platform init --with-crossplane`, `crossplane_aws` (vendor `aws`) for the environments in a cloud account. Its status sums up all of them.

## Statuses

### Active

Every driver has a ready replica, and what the capability needs is configured. `identity` stays `Active` without the Google identity provider (sign-in with a password works); the detail says `without Google IdP` and the fix is `platform init` with `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` set.

### NotConfigured

The drivers run, but nothing an operator configures is there yet:

| Capability | Missing | Fix |
|---|---|---|
| `scm` | any connection | `platform scm connection add <name> --org <org>` |
| `registry` | any registry | `platform registry add <name> --scm-connection <connection> --default` |
| `build` | `scm` or `registry` | their fix: a build runs through a connection and pushes to a registry |
| `cloud-account` | a base identity | `platform init --aws-profile <profile>` |

### Degraded

Part of the capability works and part does not: a driver without a ready replica next to one that has it, or a connection or a registry that is not `Ready` (the detail counts them, `fix` names each one), or registries with none as the default (a build without `--registry` is refused with `NoDefaultRegistry`; the fix is `platform registry set-default <name>`). `build` is `Degraded` with `scm` or `registry`, naming what it waits on. A cloud account that is not `Ready` does not degrade `cloud-account`: the platform side works, and the account is its owner's to fix.

### Unreachable

The capability is installed, but none of its drivers has a ready replica. The detail gives the replicas of each one; `kubectl --context k3d-platform-local --namespace platform-system get pods` shows why.

### NoProviderForCapability

No Deployment implements the capability: it is not installed. `cloud-account` is in this state until `platform init --aws-profile` installs its provider.

Its writes are refused before anything is stored, since nothing would ever reconcile them (ADR 0034 §4): every `POST`, `PUT` and `DELETE` of the subsystem answers `503`, with the code `NoProviderForCapability` in the JSON body:

``` { .text .output title="output" }
✗ 503: capability 'cloud-account' has no provider installed: see platform status cloud-account
```

| Capability | Refused |
|---|---|
| `scm` | `scm connection add`, `verify`, `default`, `remove`; `catalog component create` (it creates the repo through a connection) |
| `registry` | `registry add`, `set-default`, `remove` |
| `build` | `build create` |
| `cloud-account` | `cloud account add`, `verify`, `remove` |
| `resources` | `environment policy set`, `environment profile policy set` |
| `workload` | `workload deploy`, `rollback`, `remove`, `apply`, `route` (and `route --clear`) |
| `observability` | `workload signals`: a read, refused because without Prometheus there is nothing to read |

Other reads (`list`, `get`, `history`) still answer: what exists stays visible. `Unreachable` and `NotConfigured` refuse nothing: the request is stored and waits for its provider.

## Errors

| Error | Cause |
|---|---|
| `404: capability 'x' not found (capabilities: …)` | a name outside the list above |
| `not logged in: run 'platform login'` | no session |
