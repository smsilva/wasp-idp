# What the platform can do

Right after `init`, some capabilities already work and others wait for an admin to configure them. `platform status` shows each one, who implements it and whether it works:

```bash
platform status
```

``` { .text .output title="output" }
CAPABILITY     STATUS                   PROVIDERS       DETAIL
identity       Active                   keycloak        —
catalog        Active                   platform-api    —
environment    Active                   local_vcluster  —
scm            NotConfigured            scm_github      no connection ready
registry       NotConfigured            registry        no registry
build          NotConfigured            scm_github      needs scm; needs registry
cloud-account  NoProviderForCapability  —               not installed
resources      Active                   forager         —
workload       Active                   workload        —
observability  Active                   prometheus      —
✗ 3 of 9 installed capabilities not Active: scm, registry, build
  details and the fix: platform status <capability>
```

- `scm` runs (its provider is up) but has no connection yet: [SCM connection](../scm-connection/github/create-app.md) adds one, and [Registry](../registry/ghcr/register.md) the GHCR of its org right after. `build` runs through the connection and pushes to the registry, so it waits on both.
- `cloud-account` is not installed: `init` installs its provider with `--aws-profile`, in [Base credential](../cloud-accounts/aws/base-credential.md). A capability that is not installed does not make the exit code `1`; one installed and not `Active` does.

The next page opens one capability in full, with the command that fixes it.
