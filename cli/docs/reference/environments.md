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
