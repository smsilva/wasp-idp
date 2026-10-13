# Register the GHCR of the GitHub org

A build pushes its image to an **OCI registry** that the platform knows (ADR 0037). The repos of `wasp-foundry` build on GitHub Actions, and their `GITHUB_TOKEN` writes only to the GHCR of the org that owns the repo: `ghcr.io/wasp-foundry`. That is the registry to register.

``` { .text .plan title="what will be created" }
ghcr-wasp-foundry   registry · the default
└── ghcr.io/wasp-foundry   pushed by the CI of the wasp-foundry repos
```

=== "From the connection"

    The [connection](../../scm-connection/github/verify.md) already knows the org, and `verify` suggested this command:

    ```bash
    platform registry add ghcr-wasp-foundry \
      --scm-connection wasp-foundry \
      --default
    ```

    ``` { .text .output title="output" }
    ✓ registry ghcr-wasp-foundry added (default) · ghcr.io/wasp-foundry, pushed by the CI of wasp-foundry repos
    ```

    `--scm-connection` fills the vendor (`ghcr`), the host (`ghcr.io`) and the namespace (the org) at creation. The registry keeps no link to the connection: removing the connection leaves it.

=== "Explicit vendor and namespace"

    Without a connection, name the vendor and the org:

    ```bash
    platform registry add ghcr-wasp-foundry \
      --vendor ghcr \
      --namespace wasp-foundry \
      --default
    ```

    ``` { .text .output title="output" }
    ✓ registry ghcr-wasp-foundry added (default) · ghcr.io/wasp-foundry, pushed by the CI of wasp-foundry repos
    ```

    The host of `ghcr` is fixed (`ghcr.io`), so `--host` is not needed.

Adding, removing and changing the default is for `platform-admins`. The reference is [Registries](../../../reference/registries.md).
