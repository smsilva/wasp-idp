# Roll back and remove

Deploy `feat/greetings` again with one replica, then roll back. Without `--revision`, `rollback` goes back to the revision that succeeded before the running one: revision 1, with its 2 replicas.

```bash
platform workload deploy \
  --component hello-api \
  --environment demo \
  --branch feat/greetings \
  --replicas 1 \
  --wait

platform workload rollback hello-api \
  --environment demo \
  --wait

platform catalog component get hello-api
```

``` { .text .output title="output" }
✓ hello-api@demo revision 3: 0.1.0-greetings.b5f9569 running · 1/1 replicas available
  url           http://hello-api.demo.localhost:7080/
  resource      db (postgres, provision): Ready
  resource      dns (dns, provision): Ready
  resource      route (route, provision): Ready
✓ hello-api@demo revision 4: 0.1.0-greetings.b5f9569 running · 2/2 replicas available
  url           http://hello-api.demo.localhost:7080/
  resource      db (postgres, provision): Ready
  resource      dns (dns, provision): Ready
  resource      route (route, provision): Ready
component/hello-api
  system       greeter
  owner        team-alpha
  ...
  running in   demo (0.1.0-greetings.b5f9569, Available)
```

- A rollback is a **new revision** (4) that copies the version and the overrides of revision 1, as `helm rollback` does: the history only moves forward.
- `--revision <n>` picks the revision; a revision that did not succeed (like 2) or a remove is refused with `409`.
- `running in` lists only the environments you can use.

Remove the workload from the environment:

```bash
platform workload remove hello-api \
  --environment demo \
  --wait

platform workload history \
  --environment demo
```

``` { .text .output title="output" }
✓ hello-api@demo revision 5: removed from demo
WORKLOAD        REVISION  ACTION    VERSION                  STATUS                 BY               CREATED
hello-api@demo  1         deploy    0.1.0-greetings.b5f9569  Succeeded              dev@example.com  2026-10-12T19:02:42Z
hello-api@demo  2         deploy    0.1.0-redis.b5f9569      ResourcesNotSupported  dev@example.com  2026-10-12T19:03:44Z
hello-api@demo  3         deploy    0.1.0-greetings.b5f9569  Succeeded              dev@example.com  2026-10-12T19:03:54Z
hello-api@demo  4         rollback  0.1.0-greetings.b5f9569  Succeeded              dev@example.com  2026-10-12T19:04:13Z
hello-api@demo  5         remove    —                        Succeeded              dev@example.com  2026-10-12T19:04:41Z
```

The Deployment, the Service and the resources leave the vcluster (the database with its data) and `workload list` no longer shows `hello-api@demo`; the revisions stay until the environment is deleted ([Delete the environments](../cleanup/environments.md)).
