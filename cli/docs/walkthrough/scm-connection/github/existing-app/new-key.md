# Generate a new key for the App

If the org already has the platform's GitHub App, such as `wasp-foundry-platform` created before a `k3d cluster delete`, reuse it instead of creating another one. The App lives on GitHub, not in the cluster, so it is still there; only its private key was lost with the cluster.

Open the App settings on GitHub, at org **Settings → Developer settings → GitHub Apps → `<org>-platform` → Edit**. For the example:

```text
https://github.com/organizations/wasp-foundry/settings/apps/wasp-foundry-platform
```

1. Copy the **App ID**, at the top of **General**.
2. In **Private keys**, click **Generate a private key**. The browser downloads `<app>.<date>.private-key.pem`.
3. Delete the old key from the same list: nobody holds it anymore.

!!! tip
    To start over with a new App instead, delete the existing one (**Advanced → Delete GitHub App**) and go back to [Connect the platform to GitHub](../create-app.md).
