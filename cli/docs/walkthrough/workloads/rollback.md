# Roll back and remove

Deploy `0.3.0` again with one replica, then roll back. Without `--revision`, `rollback` goes back to the revision that succeeded before the running one: revision 1, with its 2 replicas.

```bash
platform workload deploy \
  --component hello-api \
  --environment demo \
  --version 0.3.0 \
  --replicas 1 \
  --wait

platform workload rollback \
  --component hello-api \
  --environment demo \
  --wait

platform catalog component get hello-api
```

``` { .text .output title="output" }
✓ hello-api@demo revision 3: 0.3.0 running · 1/1 replicas available
  url           http://hello-api.apps:80
✓ hello-api@demo revision 4: 0.3.0 running · 2/2 replicas available
  url           http://hello-api.apps:80
component/hello-api
  system       greeter
  owner        team-alpha
  ...
  running in   demo (0.3.0, Available)
```

- A rollback is a **new revision** (4) that copies the version and the overrides of revision 1, as `helm rollback` does: the history only moves forward.
- `--revision <n>` picks the revision; a revision that did not succeed (like 2) or a remove is refused with `409`.
- `running in` lists only the environments you can use.

Remove the workload from the environment:

```bash
platform workload remove \
  --component hello-api \
  --environment demo \
  --wait

platform workload history \
  --environment demo
```

``` { .text .output title="output" }
✓ hello-api@demo revision 5: removed from demo
WORKLOAD        REVISION  ACTION    VERSION  STATUS                 BY               CREATED
hello-api@demo  1         deploy    0.3.0    Succeeded              dev@example.com  2026-10-11T22:04:48Z
hello-api@demo  2         deploy    0.4.0    ResourcesNotSupported  dev@example.com  2026-10-11T22:04:54Z
hello-api@demo  3         deploy    0.3.0    Succeeded              dev@example.com  2026-10-11T22:04:58Z
hello-api@demo  4         rollback  0.3.0    Succeeded              dev@example.com  2026-10-11T22:05:04Z
hello-api@demo  5         remove    —        Succeeded              dev@example.com  2026-10-11T22:05:22Z
```

The Deployment and the Service leave the vcluster and `workload list` no longer shows `hello-api@demo`; the revisions stay until the environment is deleted ([Clean up](../cleanup.md)).
