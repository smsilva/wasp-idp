# Connect the platform to GitHub

The connection is a GitHub App: it tells the platform **which org to create repos in** and **with which credential** (ADR 0025). Only `platform-admins` manage it.

``` { .text .plan title="what will be created" }
wasp-foundry                connection · the default
└── wasp-foundry-platform   GitHub App of the wasp-foundry org, on all repositories
```

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

!!! tip
    `--no-browser` only prints the URL, to open on another machine. It is **single-use** and valid for **10 minutes**.
