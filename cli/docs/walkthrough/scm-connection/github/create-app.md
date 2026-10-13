# Connect the platform to GitHub

The connection is a GitHub App: it tells the platform **which org to create repos in** and **with which credential** (ADR 0025). Only `platform-admins` manage it.

``` { .text .plan title="what will be created" }
wasp-foundry                connection · the default
└── wasp-foundry-platform   GitHub App of the wasp-foundry org, on all repositories
```

!!! note "The App already exists?"
    After a cluster recreated from scratch, the App is still on GitHub but its key is gone. Go to [Reuse an existing App](existing-app/new-key.md) instead.

```bash
platform scm connection add wasp-foundry \
  --vendor github \
  --org wasp-foundry \
  --default
```

``` { .text .output title="output" }
→ opening the browser to create the GitHub App "wasp-foundry-platform" …
✓ app created (id 5274859) · private key stored by the platform
→ install it on the org: https://github.com/apps/wasp-foundry-platform/installations/new
  then run: platform scm connection verify wasp-foundry --wait
```

The browser opens GitHub with the App **manifest**: name and permissions are already filled in. An **org owner** confirms at **Create GitHub App for wasp-foundry**.

![GitHub screen to create the wasp-foundry-platform App from the manifest](../../images/scm-01-create-app.png){ .screenshot loading=lazy width="540" }

GitHub hands the private key **straight to the platform**: it never passes through your machine.

!!! tip
    `--no-browser` only prints the URL, to open on another machine. It is **single-use** and valid for **10 minutes**.

Next: [Install the App on the org](install.md).
