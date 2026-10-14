# New key for an existing App

Use this page when the org already has the platform's GitHub App, for example `wasp-foundry-platform`. Reuse it with a new private key.

Open the App on GitHub: org **Settings → Developer settings → GitHub Apps → the App → Edit**.

```text
https://github.com/organizations/wasp-foundry/settings/apps/wasp-foundry-platform
```

1. Copy the **App ID**, at the top of **General**.
2. In **Private keys**, click **Generate a private key**. The browser downloads the `.pem` file.
3. Delete the old keys from the same list.

!!! tip
    Prefer a new App? Delete this one (**Advanced → Delete GitHub App**) and go back to [Connect the platform to GitHub](../create-app.md).
