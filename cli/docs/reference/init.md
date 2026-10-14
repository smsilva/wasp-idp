# Control plane

`platform init` brings up the local control plane: the `platform-local` k3d cluster, the CRDs, Keycloak, the Platform API, the `local_vcluster` and `scm_github` providers and, with an AWS credential, the `aws_account` provider; with `--with-crossplane`, Crossplane and the `crossplane_aws` provider.

```bash
platform init \
  --target local \
  --admin you@example.com
```

| Flag | Meaning |
|---|---|
| `--target local` | the only target today |
| `--admin <email>` | joins `platform-admins` on its first Google sign-in; other users land only in `platform-users` |
| `--aws-profile <profile>` | the credential of that `~/.aws` profile becomes the platform base credential for [cloud accounts](cloud-accounts.md) |
| `--with-crossplane` | installs Crossplane `2.3.1`, its `provider-aws-ec2` `v2.5.1` and the `crossplane_aws` provider, so [environments can be created in a cloud account](environments.md#in-a-cloud-account); needs the base credential (`--aws-profile` now or on an earlier run) |

## Google sign-in

Export the OAuth client before `init`; the Google side is in `platform/keycloak/README.md`. Without it, `init` brings everything up and warns that Google sign-in is disabled.

```bash
export GOOGLE_CLIENT_ID=<id>.apps.googleusercontent.com

export GOOGLE_CLIENT_SECRET=<secret>
```

## Images

`init` builds every image (the Platform API and each provider) in parallel, then imports into `platform-local`, in one `k3d image import`, only the ones its nodes lack. Each image is tagged by its image id, so an unchanged project is neither imported nor rolled out again: a re-run with nothing changed takes well under a minute.

## Timings

`init` ends with the wall time of each step (cluster, CRDs, Keycloak, the image builds, the image import, each rollout, Traefik, shared-pg, Prometheus, templates) and the total, so a slower build or provider shows up from one run to the next. When a step fails, the summary shows the steps run so far, the failing one included. With `--output json`, the same numbers come in `timings` (`steps[].step`, `steps[].seconds`, `total_seconds`).

## What `init` remembers

`--admin`, the Google credentials, the AWS base credential and `--with-crossplane` are stored in the cluster, so later runs do not repeat them; each run copies the base credential to Crossplane again. Running `init` again is safe: the cluster is reused.

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
