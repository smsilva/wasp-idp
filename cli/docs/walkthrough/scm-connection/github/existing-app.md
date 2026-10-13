# Reuse an existing App

The `wasp-foundry-platform` App lives on GitHub, not in the cluster: after `k3d cluster delete` it is still there, but its private key is gone. Creating it again through the browser fails with **Name is already taken**. Instead, give the platform the App id and a new key.

## 1. Get the App id and a new key

Open the App on GitHub: org **Settings → Developer settings → GitHub Apps → wasp-foundry-platform → Edit** (`https://github.com/organizations/wasp-foundry/settings/apps/wasp-foundry-platform`).

- **App ID**: at the top of **General**.
- **Private keys → Generate a private key**: the browser downloads `wasp-foundry-platform.<date>.private-key.pem`.
- While there, delete the old key from the list: nobody holds it anymore.

## 2. Register the connection

If an earlier `add` through the browser left the connection in `AppNotCreated`, remove it first:

```bash
platform scm connection remove wasp-foundry
```

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

An App still installed on the org goes straight to `ready`: skip [Install the App on the org](install.md). Otherwise `--wait` stays at `NotInstalled` until it is installed.

## 3. Delete the downloaded key

The platform keeps its own copy, in a Secret only the controller reads.

```bash
rm ~/Downloads/wasp-foundry-platform.*.private-key.pem
```

!!! tip
    Starting over without the old App: delete it (**Settings → GitHub Apps → wasp-foundry-platform → Advanced → Delete GitHub App**) and go back to [Connect the platform to GitHub](create-app.md).
