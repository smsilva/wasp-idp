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

One capability in full, with the command that fixes it:

```bash
platform status scm
```

``` { .text .output title="output" }
scm  NotConfigured
  depends on    identity, catalog
  detail        no connection ready
  fix           platform scm connection add <name> --org <org>

  DRIVER  PROVIDER    VERSION       REPLICAS  STATUS
  github  scm_github  b0333f5c90be  1/1       Active
```

- A capability can have one **driver** per vendor: a Bitbucket driver would be one more line here, and the connections of both vendors are listed under it. `--verbose` prints every capability this way.
- The version is the tag of the provider's image, which `init` builds.
- A regular user sees only `CAPABILITY` and `STATUS`, and `ask a platform-admin to configure it` under one that is not `Active`.

The statuses and what each capability needs are in the [reference](../../reference/status.md).

The next steps configure each one; [The platform is ready](../ready.md) runs `platform status` again at the end.
