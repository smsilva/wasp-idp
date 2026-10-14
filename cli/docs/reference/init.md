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
| `--with-crossplane` | installs Crossplane `2.3.1`, its `provider-aws-ec2` `v2.5.1` and the `crossplane_aws` provider, so [environments can be created in a cloud account](environments.md#in-a-cloud-account); needs the base credential (`--aws-profile` now or on an earlier run) |

## Settings file

`init` takes each setting from the first place that has it: the flag, the settings file, what an earlier `init` stored in the cluster, the default. `--file` reads only that file; without it, `init` reads `~/.config/platform/init.yaml` when it exists (it follows `XDG_CONFIG_HOME`).

```yaml
apiVersion: platform.wasp.silvios.me/v1alpha1
kind: InitConfig
target: local
admins:
  - you@example.com
awsProfile: null
withCrossplane: false
```

A key it does not know, or an admin that is not an e-mail, stops `init` before any step. Secrets stay out of the file: the Google credentials come from the environment (below).

Before the install, `init` prints each setting and its source, so a forgotten file never applies unseen, and asks `Proceed?`:

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

`init` runs its steps side by side, each one as soon as what it needs is done: the image builds and the cluster first; then, once the CRDs are applied, Keycloak, Traefik, shared-pg and Prometheus together; each provider once its image is in the cluster (providers need neither Keycloak nor the API); the Platform API last, once Keycloak's realm is imported. With `--with-crossplane`, Crossplane comes up beside them, after the `aws_account` provider stores the base credential. Each step prints one line when it starts (`▶`) and one when it ends (`✓`, with its time). The first step that fails (`✗`) stops the others and is the only error reported.

## Images

`init` builds every image (the Platform API and each provider) in parallel, while the cluster comes up, then imports into `platform-local`, in one `k3d image import`, only the ones its nodes lack. Each image is tagged by its image id, so an unchanged project is neither imported nor rolled out again: a re-run with nothing changed takes well under a minute.

## Timings

`init` ends with the wall time of each step (cluster, CRDs, Keycloak, the image builds, the image import, each rollout, Traefik, shared-pg, Prometheus, templates) and the total, so a slower build or provider shows up from one run to the next. When a step fails, the summary shows the steps run so far, the failing one included. With `--output json`, the same numbers come in `timings` (`steps[].step`, `steps[].seconds`, `total_seconds`).

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
