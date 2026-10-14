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

Then check that:

- `platform whoami` shows you in `team-alpha`, the owner of the app;
- `platform catalog system get greeter` finds the system the app joins;
- `gh repo view wasp-foundry/hello-api` fails with `Could not resolve to a Repository`: that is the expected answer, since a repo left by an earlier run stops the create ([After the demo](cleanup.md));
- `ssh -T git@github.com-personal` answers with an account that is a member of `wasp-foundry` ([Clone and branch](clone.md) pushes through that alias).
