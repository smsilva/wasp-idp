# Environments

An environment is a vcluster created by the `local_vcluster` provider inside `platform-local`, or, with `--cloud-account`, a VPC in a [cloud account](cloud-accounts.md), created through Crossplane by the `crossplane_aws` provider (see [In a cloud account](#in-a-cloud-account)).

| Command | What it does |
|---|---|
| `platform environment create <name> --profile ephemeral\|shared [--expires <duration>] [--share-with <team>]... [--cloud-account <account>] [--wait]` | requests an environment, private unless shared; `--wait` waits for `ready` and writes the kubeconfig |
| `platform environment list [--all]` | NAME, PROFILE, ACCOUNT, STATUS, EXPIRES, OWNER, SHARED: yours and your teams'; `--all` (the default for `platform-admins`) shows every environment, without kubeconfig |
| `platform environment get <name>` | status, message and where its workloads are reached (`http://*.<name>.localhost:7080`), or its VPC and region in a cloud account; writes your kubeconfig when ready |
| `platform environment get <name> --admin` | writes the vcluster admin kubeconfig (`platform-admins` only) |
| `platform environment share\|unshare <name> --team <team>` | see [Teams](teams.md#sharing-environments) |
| `platform environment credential <name>` | a 10-minute token as an `ExecCredential`; called by kubectl through the kubeconfig |
| `platform environment policy get <name>` | the binding policy of the environment, then the one of its profile and the platform default (LAYER `environment`, `profile`, `default`; TYPE, CLASS, ID, MODE, PARAMS) |
| `platform environment policy set <name> --file <file\|->` | replaces the policy with the `provisioners` list of the file; an empty list removes it (`platform-admins` only) |
| `platform environment profile policy get <profile>` | the binding policy of a profile (`ephemeral`, `shared`), then the platform default; anyone signed in |
| `platform environment profile policy set <profile> --file <file\|->` | replaces the policy of the profile for all its environments; an empty list removes it (`platform-admins` only) |
| `platform environment delete <name>` | removes the environment and the vcluster, or the VPC in a cloud account |

`--expires` takes `30m`, `12h`, `3d` or `1w`; the provider deletes the environment when the deadline passes (checked every 10 s).

## In a cloud account

`--cloud-account <account>` provisions the environment in that account instead of a local vcluster (#435): the `crossplane_aws` provider (ADR 0032, #436) creates one VPC (`10.0.0.0/16`, no cost) in the first region of the account, through a Crossplane `ProviderConfig` named after the account that assumes its role with the ExternalId. A cluster in it comes later.

- On create, the account must exist, be `ready` and have a region (`422` otherwise), and you must be able to use it: owner, `platform-admins`, or a member of a team it is shared with (`403` otherwise). This is checked only at creation: an unshare never takes down environments already there.
- The account is immutable: the CRD refuses changing, adding or removing `spec.cloudAccount`.
- Without `platform init --with-crossplane`, nothing creates it, and it stays `NoProviderForCapability`; `--wait` gives up after 60 s in that status instead of waiting out `--timeout`.
- It is `ready` once Crossplane reports the VPC `Ready` (the message of `get` names the VPC and its region; `--output json` has them in `cloud`); `CloudAccountNotReady` while the account is not `ready` and the VPC was not created yet; `ProvisioningFailed` with the Crossplane message when AWS refuses (a role without `ec2:CreateVpc`, for example).
- `delete` removes the VPC in the account first; the environment goes once Crossplane confirms it is gone.
- The provider creates the VPC only in the exact account the API authorized on create (its uid is kept on the environment): an environment written around the API, or an account removed and registered again under the same name, gets `ProvisioningFailed`.
- `--expires` holds as for any environment: `local_vcluster` deletes it when the deadline passes, and the VPC goes with the `crossplane_aws` finalizer.
- It has no vcluster: `get` writes no kubeconfig, and `get --admin`, `credential` and the workload writes (`deploy`, `apply`, `remove`, `route set|delete`) answer `409`.
- `platform cloud account remove <account>` answers `409` while an environment references it.

## Status

| Status | Meaning |
|---|---|
| `NoProviderForCapability` | no provider has picked up the request yet |
| `Provisioning` | vcluster being created, then the mesh and the gateway installed in it (about 60 s); in a cloud account, the VPC being created |
| `ready` | vcluster, `istiod` and the gateway up; `get` or `--wait` writes the kubeconfig. In a cloud account: the VPC exists |
| `CloudAccountNotReady` | in a cloud account: the account is not `ready` (or is gone), so nothing was created yet |
| `ProvisioningFailed` | provider error; see `message` in the JSON |
| `deleting` | removal in progress |

## Kubeconfig

| File | Who gets it | Credential |
|---|---|---|
| `~/.config/platform/environments/<name>.kubeconfig` | the owner, `platform-admins`, members of the teams it is shared with | none stored: kubectl runs `platform environment credential <name>` on every command, and the API returns a 10-minute token if you still have access (ADR 0028) |
| `~/.config/platform/environments/<name>-admin.kubeconfig` | `platform-admins` | the vcluster admin certificate, without going through the API |

With the personal kubeconfig, the CLI must be installed and signed in where kubectl runs. Inside the vcluster you are the ServiceAccount `platform-identities/<sub>`, with `cluster-admin`; `kubectl auth whoami` shows it.

Each environment gets one port from `127.0.0.1:7100`–`7119`. The pods run in the outer cluster, in the namespace `env-<name>`.

## What a pod may not do

`cluster-admin` in the vcluster does not reach the host: every pod follows the Pod Security Standard `baseline` (ADR 0041). A pod is refused at apply when it asks for:

- `hostNetwork`, `hostPID` or `hostIPC`;
- a `privileged` container, or `windowsOptions.hostProcess`;
- a `hostPath` volume or a `hostPort`;
- a capability outside the `baseline` set, `NET_ADMIN` and `NET_RAW` (the `istio-init` container of the mesh needs those two);
- `procMount` other than `Default`, seccomp or AppArmor `Unconfined`, SELinux `user`/`role`, or a sysctl outside the safe list.

```text
pods "web" is forbidden: ValidatingAdmissionPolicy 'platform-environment-pod-security' with binding 'platform-environment-pod-security' denied request: hostNetwork, hostPID and hostIPC are not allowed in an environment
```

The same policy runs on the host for the pods the vcluster syncs, so deleting it inside the vcluster changes nothing: the pod then stays `Pending`, and `kubectl describe pod` shows the refusal in its sync events.

## Entry point

Every environment is reached from outside at `http://*.<name>.localhost:7080` (ADR 0036). `*.localhost` resolves to the loopback without DNS. Port `7080` is a Traefik shared by every environment, installed by `platform init`: it sends each `*.<name>.localhost` to the `Gateway` `platform` (Istio, namespace `istio-ingress`) of that environment's vcluster. A route of a workload attaches to that `Gateway`; a host of another environment never reaches it.

## Permissions

| Action | Who |
|---|---|
| create, list, get | any user (list and get only what they can use) |
| delete, share, unshare | the owner or `platform-admins` |
| policy get | whoever uses the environment |
| policy set | `platform-admins` |

## Binding policy

Which mode makes each resource of a workload in the environment (#305). The Forager reads three layers, and the first item that matches `type`, `class` and `id` wins:

1. the policy of the environment (`env-<name>`), set with `environment policy set`;
2. the policy of its profile (`profile-<profile>`, #329), set with `environment profile policy set`. `platform init` creates `profile-ephemeral` (`postgres` → `compose` in `shared-pg`) when it is missing and never overwrites it;
3. the platform default (`platform-default`, `postgres` → `provision`).

Changing a layer does not change a resource that already exists in another mode: its next deploy ends `ResourceModeChanged`, and changing the mode takes a `workload remove` and a new deploy. Environments `ephemeral` with a database made before #329 (`provision`) get that on their next deploy.

```yaml
provisioners:
  - type: postgres        # required
    class: restored       # optional: matches only a resource that asks for this class
    id: orders-db         # optional: matches only the resource with this id in the Score
    mode: compose         # provision | compose | bind
    params:
      instance: shared-pg # compose: the shared instance, required
```

A `bind` item takes the values of the database that exists and the Secret with its password:

```yaml
  - type: postgres
    class: restored
    mode: bind
    params:
      secretRef: restored-db      # a Secret of platform-resources labeled platform.wasp.silvios.me/bindable=true, key password
      host: shared-pg.resources
      port: "5432"                # optional, 5432 by default
      database: restored
      username: restored
```

| Mode | `postgres` |
|---|---|
| `provision` | a Postgres of its own in the vcluster, namespace `resources` |
| `compose` | a role and a database in the shared instance `params.instance` (`shared-pg`) |
| `bind` | the database that already exists in the item's `params`; only the password of `params.secretRef` is copied to the vcluster, and nothing is created or dropped |

A resource keeps the mode and the class it was created with: a policy or a `--resource-class` that changes them ends the next deploy as `ResourceModeChanged`, until `workload remove`. `bind` without `secretRef`, `host`, `database` and `username` is refused (`422`). Walkthroughs: [A database in the shared instance](../walkthrough/workloads/resources/compose.md) and [A database that already exists](../walkthrough/workloads/resources/bind.md).
