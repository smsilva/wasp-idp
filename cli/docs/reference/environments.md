# Environments

An environment is a vcluster created by the `local_vcluster` provider inside `platform-local`.

| Command | What it does |
|---|---|
| `platform environment create <name> --profile ephemeral\|shared [--expires <duration>] [--share-with <team>]... [--wait]` | requests an environment, private unless shared; `--wait` waits for `ready` and writes the kubeconfig |
| `platform environment list [--all]` | NAME, PROFILE, STATUS, EXPIRES, OWNER, SHARED: yours and your teams'; `--all` (the default for `platform-admins`) shows every environment, without kubeconfig |
| `platform environment get <name>` | status and message; writes your kubeconfig when ready |
| `platform environment get <name> --admin` | writes the vcluster admin kubeconfig (`platform-admins` only) |
| `platform environment share\|unshare <name> --team <team>` | see [Teams](teams.md#sharing-environments) |
| `platform environment credential <name>` | a 10-minute token as an `ExecCredential`; called by kubectl through the kubeconfig |
| `platform environment policy get <name>` | the binding policy of the environment, then the platform default (LAYER, TYPE, CLASS, ID, MODE, PARAMS) |
| `platform environment policy set <name> --file <file\|->` | replaces the policy with the `provisioners` list of the file; an empty list removes it (`platform-admins` only) |
| `platform environment delete <name>` | removes the environment and the vcluster |

`--expires` takes `30m`, `12h`, `3d` or `1w`; the provider deletes the environment when the deadline passes (checked every 10 s).

## Status

| Status | Meaning |
|---|---|
| `NoProviderForCapability` | no provider has picked up the request yet |
| `Provisioning` | vcluster being created (about 30 s) |
| `ready` | vcluster up; `get` or `--wait` writes the kubeconfig |
| `ProvisioningFailed` | provider error; see `message` in the JSON |
| `deleting` | removal in progress |

## Kubeconfig

| File | Who gets it | Credential |
|---|---|---|
| `~/.config/platform/environments/<name>.kubeconfig` | the owner, `platform-admins`, members of the teams it is shared with | none stored: kubectl runs `platform environment credential <name>` on every command, and the API returns a 10-minute token if you still have access (ADR 0028) |
| `~/.config/platform/environments/<name>-admin.kubeconfig` | `platform-admins` | the vcluster admin certificate, without going through the API |

With the personal kubeconfig, the CLI must be installed and signed in where kubectl runs. Inside the vcluster you are the ServiceAccount `platform-identities/<sub>`, with `cluster-admin`; `kubectl auth whoami` shows it.

Each environment gets one port from `127.0.0.1:7100`–`7119`. The pods run in the outer cluster, in the namespace `env-<name>`.

## Permissions

| Action | Who |
|---|---|
| create, list, get | any user (list and get only what they can use) |
| delete, share, unshare | the owner or `platform-admins` |
| policy get | whoever uses the environment |
| policy set | `platform-admins` |

## Binding policy

Which mode makes each resource of a workload in the environment (#305). The Forager reads the policy of the environment before the platform default (`platform-default`, `postgres` → `provision`); the first item that matches `type`, `class` and `id` wins.

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

A resource keeps the mode and the class it was created with: a policy or a `--resource-class` that changes them ends the next deploy as `ResourceModeChanged`, until `workload remove`. `bind` without `secretRef`, `host`, `database` and `username` is refused (`422`). Walkthroughs: [21.8](../walkthrough/workloads/21-8-compose.md) and [21.9](../walkthrough/workloads/21-9-bind.md).
