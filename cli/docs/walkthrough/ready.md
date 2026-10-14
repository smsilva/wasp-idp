# The platform is ready

Configuration ends where [What the platform can do](login/status.md) started: `platform status`, now with the connection and the registry in place.

```bash
platform status
```

``` { .text .output title="output" }
CAPABILITY     STATUS                   PROVIDERS       DETAIL
identity       Active                   keycloak        —
catalog        Active                   platform-api    —
environment    Active                   local_vcluster  —
scm            Active                   scm_github      wasp-foundry (default)
registry       Active                   registry        ghcr-wasp-foundry (default)
build          Active                   scm_github      —
cloud-account  NoProviderForCapability  —               not installed
resources      Active                   forager         —
workload       Active                   workload        —
observability  Active                   prometheus      —
✓ all 9 installed capabilities Active (1 not installed: cloud-account)
```

Nothing below needs `cloud-account`.

From here on, the walkthrough follows a **developer** of `team-alpha`: a component from a template, a build, an environment to run it, and the deploy.
