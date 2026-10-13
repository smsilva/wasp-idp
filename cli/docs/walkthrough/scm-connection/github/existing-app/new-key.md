# Generate a new key for the App

The `wasp-foundry-platform` App lives on GitHub, not in the cluster. After `k3d cluster delete` it is still there, but its private key is gone with the cluster. The platform needs a new one.

Open the App on GitHub:

```text
https://github.com/organizations/wasp-foundry/settings/apps/wasp-foundry-platform
```

1. Copy the **App ID**, at the top of **General**.
2. In **Private keys**, click **Generate a private key**. The browser downloads `wasp-foundry-platform.<date>.private-key.pem`.
3. Delete the old key from the same list: nobody holds it anymore.

!!! tip
    To start over with a new App instead, delete this one (**Advanced → Delete GitHub App**) and go back to [Connect the platform to GitHub](../create-app.md).
