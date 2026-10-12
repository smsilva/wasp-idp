# The history of a workload

A deploy can fail after the build passed: here, a version whose Score asks for a resource of type `redis`, which no binding policy resolves. The build refuses `redis` ([What a build refuses](../builds/refused.md)), so this one version is staged: `0.1.0-redis.b5f9569` is the `Version` of `feat/greetings` copied by `kubectl` with `db` of type `redis`. Deploy it:

```bash
platform workload deploy \
  --component hello-api \
  --environment demo \
  --version 0.1.0-redis.b5f9569 \
  --wait

platform workload history \
  --environment demo \
  --component hello-api
```

``` { .text .output title="output" }
✗ hello-api@demo revision 2: ResourcesNotSupported: db: no provisioner for redis in demo
WORKLOAD        REVISION  ACTION  VERSION                  STATUS                 BY               CREATED
hello-api@demo  1         deploy  0.1.0-greetings.b5f9569  Succeeded              dev@example.com  2026-10-12T19:02:42Z
hello-api@demo  2         deploy  0.1.0-redis.b5f9569      ResourcesNotSupported  dev@example.com  2026-10-12T19:03:44Z
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
| a resource type with no provisioner in the environment (`redis`) | revision `ResourcesNotSupported` |
| a resource whose mode would change ([A database for a workload](resources.md)) | revision `ResourceModeChanged` |
| a provisioner that failed | revision `ResourcesFailed` |
| a Score field outside phase 1 (anything but `containers` with image, command, args, variables, resources and `httpGet` probes, and `service.ports`) | revision `UnsupportedSpec` |
| a rollout with no progress for 120 s (an image the vcluster cannot pull, a crash loop) | revision `RolloutFailed` |
