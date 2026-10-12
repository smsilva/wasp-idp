# The history of a workload

Version `0.4.0` of `hello-api` keeps the resources of the template in its Score: `db`, `dns` and `route`. Only `postgres` has a provider so far. Deploy it:

```bash
platform workload deploy \
  --component hello-api \
  --environment demo \
  --version 0.4.0 \
  --wait

platform workload history \
  --environment demo \
  --component hello-api
```

``` { .text .output title="output" }
✗ hello-api@demo revision 2: ResourcesNotSupported: dns: no provisioner for dns in demo
WORKLOAD        REVISION  ACTION  VERSION  STATUS                 BY                     CREATED
hello-api@demo  1         deploy  0.3.0    Succeeded              dev@example.com        2026-10-11T21:28:36Z
hello-api@demo  2         deploy  0.4.0    ResourcesNotSupported  dev@example.com        2026-10-11T21:28:54Z
```

- A revision that fails changes nothing in the vcluster: `hello-api@demo` still runs revision 1, and `workload get` shows revision 2 on a `newest` line.
- `history` without `--component` lists every workload of the environment.

What a deploy refuses:

| Refusal | Where |
|---|---|
| a user outside the owner team of the component | `403`, before any revision |
| no access to the environment | `403` |
| a version or branch with no version in the index | `404` |
| a version indexed before the index kept the spec | `409` `SpecNotIndexed` |
| a resource type with no provisioner in the environment (`dns`, `route`) | revision `ResourcesNotSupported` |
| a resource whose mode would change (step 21.7) | revision `ResourceModeChanged` |
| a provisioner that failed | revision `ResourcesFailed` |
| a Score field outside phase 1 (anything but `containers` with image, command, args, variables, resources and `httpGet` probes, and `service.ports`) | revision `UnsupportedSpec` |
| a rollout with no progress for 120 s (an image the vcluster cannot pull, a crash loop) | revision `RolloutFailed` |
