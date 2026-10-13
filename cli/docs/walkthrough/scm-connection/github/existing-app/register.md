# Register the existing App

Give the platform the App ID and the key you just downloaded:

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

An App still installed on the org goes straight to `ready`. If it was uninstalled, `--wait` stays at `NotInstalled`: [install it on the org](../install.md).

!!! note "Refused because the name exists?"
    An earlier `add` through the browser leaves the connection in `AppNotCreated`. Remove it and run `add` again:

    ```bash
    platform scm connection remove wasp-foundry
    ```
