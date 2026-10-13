# Register the existing App

Give the platform the **App ID** and the **key file** from the previous page:

```bash
platform scm connection add wasp-foundry \
  --vendor github \
  --org wasp-foundry \
  --app-id 5274859 \
  --private-key-file ~/Downloads/wasp-foundry-platform.2026-10-13.private-key.pem \
  --default \
  --wait
```

``` { .text .output title="output" }
✓ connection wasp-foundry registered with App 5274859 · private key stored by the platform
✓ wasp-foundry ready (wasp-foundry, all repositories)
→ register its GHCR, where builds of wasp-foundry repos push: platform registry add ghcr-wasp-foundry --scm-connection wasp-foundry --default
```

- **Still installed on the org**: the connection goes straight to `ready`.
- **Not installed**: `--wait` stops at `NotInstalled`. [Install the App on the org](../install.md).

!!! note "`connection 'wasp-foundry' already exists`?"
    An earlier `add` through the browser left the connection behind. Remove it and run `add` again:

    ```bash
    platform scm connection remove wasp-foundry
    ```
