# Control plane

`platform init` brings up the local control plane: the `platform-local` k3d cluster, the CRDs, Keycloak, the Platform API, the `local_vcluster` and `scm_github` providers and, with an AWS credential, the `aws_account` provider; with `--with-crossplane`, Crossplane and the `crossplane_aws` provider.

```bash
platform init \
  --admin you@example.com \
  --yes
```

| Flag | Meaning |
|---|---|
| `--target local` | the only target today, and the default |
| `--admin <email>` | joins `platform-admins` on its first Google sign-in; repeat it for more than one; other users land only in `platform-users`; a value that is not an e-mail stops `init` before any step |
| `--aws-profile <profile>` | the credential of that `~/.aws` profile becomes the platform base credential for [cloud accounts](cloud-accounts.md) |
| `--file <path>` | the settings file to read, or to write with `--generate-file`; default `~/.config/platform/init.yaml` |
| `--generate-file` | writes the settings (flags, then the file, then what the cluster remembers) to the file and installs nothing; refuses an existing file without `--force` |
| `--dry-run` | shows the settings and the steps `init` would run, and installs nothing; with `-o json`/`yaml`, as data |
| `--yes` | installs without asking; required without a terminal or with `-o json`/`yaml` |
| `--progress auto\|live\|plain` | how the steps show while `init` runs: `live` is a card that redraws in place, `plain` one line per step; `auto` (the default) is `live` on a terminal and `plain` otherwise (CI, a pipe, `cli-smoke`) |
| `--with-crossplane` | installs Crossplane `2.3.1`, its `provider-aws-ec2` `v2.5.1` and the `crossplane_aws` provider, so [environments can be created in a cloud account](environments.md#in-a-cloud-account); needs the base credential (`--aws-profile` now or on an earlier run) |

## Settings file

`init` takes each setting from the first place that has it: the flag, the settings file, what an earlier `init` stored in the cluster, the default. `--file` reads only that file; without it, `init` reads `~/.config/platform/init.yaml` when it exists (it follows `XDG_CONFIG_HOME`).

```yaml
apiVersion: platform.wasp.silvios.me/v1alpha1
kind: InitConfig
target: local
admins:
  - you@example.com
```

`awsProfile` and `withCrossplane` enter the file only when set (`--aws-profile`, `--with-crossplane`).

A key it does not know, or an admin that is not an e-mail, stops `init` before any step. Secrets stay out of the file: the Google credentials come from the environment (below).

Before the install, `init` prints each setting and its source, so a forgotten file never applies unseen, and asks `Proceed?`. On a terminal, the settings open the card of the run (see [Progress](#progress)); without one, they come as a table:

``` { .text .output title="output" }
SETTING          VALUE            SOURCE
target           local            default
admins           you@example.com  /home/you/.config/platform/init.yaml
aws_profile      —                default
with_crossplane  false            default
Proceed? [y/N]:
```

## Google sign-in

Export the OAuth client before `init`; the Google side is in `platform/keycloak/README.md`. Without it, `init` brings everything up and warns that Google sign-in is disabled.

```bash
export GOOGLE_CLIENT_ID=<id>.apps.googleusercontent.com

export GOOGLE_CLIENT_SECRET=<secret>
```

## Steps

`init` runs its steps side by side, each one as soon as what it needs is done: the image builds and the cluster first; then, once the CRDs are applied, Keycloak, Traefik, shared-pg and Prometheus together; each provider once its image is in the cluster (providers need neither Keycloak nor the API); the Platform API last, once Keycloak's realm is imported. With `--with-crossplane`, Crossplane comes up beside them, after the `aws_account` provider stores the base credential. The first step that fails stops the others and is the only error reported.

## Progress

On a terminal, `init` shows one card that redraws in place. It opens with the settings and the file they came from (each row shows only its source's file name, `default`, `flag` or `cluster`), then the run: the steps done out of the total, the elapsed time and how far along the last run that is; the steps running now and the next to start (at most 5, `+N more waiting` below), each with its time or the step it waits for, and a bar that fills by the time the step took in the last successful run and stops short of full until the step ends (with no last run, it pulses); a finished step leaves the list and counts in `Overall`. A step's notes (a reused cluster, a credential about to expire) close the card under `Notes`; a warning comes with `⚠` in yellow.

``` { .text .output title="output" }
╭──────────────────────────────────────────────────────────╮
│ platform init                                            │
│ local · run 2026-10-14T05-12-03 · settings from          │
│ ~/.config/platform/init.yaml                             │
│                                                          │
│ target           local                         init.yaml │
│ admins           you@example.com               init.yaml │
│ aws_profile      —                             default   │
│ with_crossplane  false                         init.yaml │
│                                                          │
│ ╭──────────────────────────────────────────────────────╮ │
│ │                                                      │ │
│ │  17 / 21  steps  13.1s  ~47% of the last run         │ │
│ │                                                      │ │
│ │  Now · 4 of 4   bar = time of the last run           │ │
│ │                                                      │ │
│ │  keycloak                                      3.3s  │ │
│ │  ▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍    │ │
│ │                                                      │ │
│ │  keycloak realm                      waits keycloak  │ │
│ │  ▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍    │ │
│ │                                                      │ │
│ │  Overall                                             │ │
│ │  ▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍▍    │ │
│ │  0 %                                          100 %  │ │
│ │                                                      │ │
│ │  ■ done 17   ■ running 1   ■ waiting 3               │ │
│ │  logs ~/.local/state/platform/init/2026-10-14T05-1…  │ │
│ │                                                      │ │
│ ╰──────────────────────────────────────────────────────╯ │
│                                                          │
│ Notes                                                    │
│ cluster        cluster platform-local already exists,    │
│                reusing it                                │
│                                                          │
╰──────────────────────────────────────────────────────────╯
```

The bars are green for done, blue for running and grey for what is left. At the end, the card shows the 3 slowest steps; when a step fails, it stays in the card in red, and `init` prints the end of its log below.

Without a terminal, or with `--progress plain`, each step prints one line when it starts (`▶`) and one when it ends (`✓`, with its time); a note of a step (a reused cluster, a credential about to expire) comes as `·`. While a step runs, a heartbeat every 30 s (`…`) shows it is waiting, not hung: a rollout, a Helm install job or the Crossplane package pull can take minutes. The output of the commands stays out of the terminal and goes to the [logs](#logs).

``` { .text .output title="output" }
05:12:03 ▶ cluster
05:12:04 · cluster                     cluster platform-local already exists, reusing it
05:12:04 ✓ cluster                        0.6s
05:12:04 ▶ keycloak
05:12:34 … keycloak                    still running [30.0s]
05:12:42 ✓ keycloak                      38.2s
```

## Logs

Every run leaves one folder under `~/.local/state/platform/init/` (it follows `XDG_STATE_HOME`), named by the time it started, with one plain-text file per step and a `run.yaml`; `latest` points at the newest. `init` keeps the last 20 runs and prints the folder at the end.

```text
~/.local/state/platform/init/
├── 2026-10-14T05-12-03/
│   ├── run.yaml
│   ├── 01-cluster.log
│   ├── 02-build-images.log
│   ├── …
│   └── 21-platform-api.log
└── latest -> 2026-10-14T05-12-03
```

- The file number is the order in which the steps started: they run side by side, so the numbers read as the story of the run.
- Each file has every command the step ran (`$ kubectl rollout status …`), with the time, its output and its exit code, and the step's notes. A command that reads a credential (a Secret value, the AWS profile) logs only the command and its exit code; the input of a command (a Secret applied through stdin) is never logged.
- `run.yaml` has the settings and their source, the result (`succeeded` or `failed`, with `failedStep` and `error`), each step with its time, its result (`done`, `failed`, or `stopped` when another step's failure ended it) and its file, and the total.

When a step fails, `init` prints the last 30 lines of its file, the path of the file and the folder of the run:

```bash
less ~/.local/state/platform/init/latest/09-keycloak.log
```

## Images

`init` builds every image (the Platform API and each provider) in parallel, while the cluster comes up, then imports into `platform-local`, in one `k3d image import`, only the ones its nodes lack. Each image is tagged by its image id, so an unchanged project is neither imported nor rolled out again: a re-run with nothing changed takes well under a minute.

## Timings

`init` ends with the wall time of each step (cluster, CRDs, Keycloak, the image builds, the image import, each rollout, Traefik, shared-pg, Prometheus, templates) and the total, so a slower build or provider shows up from one run to the next. The timings are printed in plain mode (the card shows the slowest steps instead). When a step fails, the summary shows the steps run so far, the failing one included. With `--output json`, the same numbers come in `timings` (`steps[].step`, `steps[].seconds`, `total_seconds`), the run folder in `logs`, and nothing is printed while `init` runs.

## What `init` remembers

The `--admin` e-mails (all of them: a later `--admin` replaces the list), the Google credentials, the AWS base credential and `--with-crossplane` are stored in the cluster, so later runs do not repeat them; each run copies the base credential to Crossplane again. Running `init` again is safe: the cluster is reused.

If the AWS credential is temporary (SSO or an assumed role), `init` warns when it expires and must be run again. Prefer a dedicated IAM user with permission only for `sts:AssumeRole` and `sts:GetCallerIdentity`.

## Config file

```bash
cat ~/.config/platform/config.yaml
```

``` { .yaml .output title="output" }
target: local
api_url: http://127.0.0.1:9090
context: k3d-platform-local
issuer: http://localhost:8180/realms/platform
client_id: platform-cli
```

!!! warning
    Do not run `init` with a changed Keycloak theme while someone is mid sign-in: the sign-in session lives in the Keycloak pod memory, and the Google callback hits a server that forgot it.
