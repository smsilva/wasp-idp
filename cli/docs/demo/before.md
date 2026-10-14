# Before the demo

Run these before the meeting. The demo needs the SCM connection, the registry and the catalog in place:

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

You are in `team-alpha`, the owner of the app:

```bash
platform whoami
```

The system `greeter`, which the app joins, is in the catalog:

```bash
platform catalog system get greeter
```

The repo does not exist yet. A repo left by an earlier run stops the create ([After the demo](cleanup.md)), so `Could not resolve to a Repository` is the expected answer:

```bash
gh repo view wasp-foundry/hello-api
```

The SSH alias that [Clone and branch](clone.md) pushes through answers with an account that is a member of `wasp-foundry`:

```bash
ssh -T git@github.com-personal
```
