# One capability in full

`platform status <capability>` shows what it depends on, why it is not `Active` and the command that fixes it:

```bash
platform status scm
```

``` { .text .output title="output" }
scm  NotConfigured
  depends on    identity, catalog
  detail        no connection ready
  fix           platform scm connection add <name> --org <org>

  DRIVER  PROVIDER    VERSION       REPLICAS  STATUS
  github  scm_github  8bc438d839b4  1/1       Active
```

- A capability can have one **driver** per vendor: a Bitbucket driver would be one more line here, and the connections of both vendors are listed under it. `--verbose` prints every capability this way.
- The version is the tag of the provider's image, which `init` builds.
- A regular user sees only `CAPABILITY` and `STATUS`, and `ask a platform-admin to configure it` under one that is not `Active`.

The statuses and what each capability needs are in the [reference](../../reference/status.md).

The next steps configure each one; [The platform is ready](../ready.md) runs `platform status` again at the end.
