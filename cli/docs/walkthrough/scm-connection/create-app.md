# Create the App

The connection tells the platform **which org to create repos in** and **with which credential** (ADR 0025). Only `platform-admins` manage it.

``` { .text .plan title="what will be created" }
wasp-foundry                connection · the default
└── wasp-foundry-platform   GitHub App of the wasp-foundry org, on all repositories
```

=== "New App, via the browser"

    The `add` opens the browser at the Platform API, which sends the **manifest** of the `<org>-platform` App to GitHub. GitHub returns the key **straight to the platform**, without passing through the machine of whoever runs the command.

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

    On GitHub, whoever confirms must be an **org owner**. Name and permissions already come from the manifest: just confirm at **Create GitHub App for wasp-foundry**.

    ![GitHub screen to create the wasp-foundry-platform App from the manifest](../images/scm-01-create-app.png){ .screenshot loading=lazy width="540" }

    !!! tip
        `--no-browser` only prints the URL, to open on another machine. It is **single-use** and valid for **10 minutes**; running `add` again issues another.

=== "Existing App"

    For an App created earlier, such as the `wasp-foundry-platform` of a cluster recreated from scratch. No browser flow: the platform gets the App id and a private key generated on GitHub.

    1. Open the App on GitHub: org **Settings → Developer settings → GitHub Apps → wasp-foundry-platform → Edit** (`https://github.com/organizations/wasp-foundry/settings/apps/wasp-foundry-platform`). The **App ID** is at the top of **General**.
    2. In **Private keys**, click **Generate a private key**. The browser downloads `wasp-foundry-platform.<date>.private-key.pem`.
    3. Hand both to the platform:

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

        An App still installed on the org goes straight to `ready`, and [Install on the org](install.md) is skipped. Otherwise `--wait` stays at `NotInstalled` until it is installed.

    4. Delete the downloaded file: the platform keeps its own copy, in a Secret only the controller reads.

        ```bash
        rm ~/Downloads/wasp-foundry-platform.*.private-key.pem
        ```

    !!! tip
        On the App page, **Private keys** still lists the key of the old cluster: delete it, since nobody holds it anymore.

!!! warning "A cluster recreated from scratch"
    The `<org>-platform` App lives on GitHub, not in the cluster: after `k3d cluster delete`, it is still there and its private key is gone with the cluster. A new `add` through the browser then fails on GitHub with **Name is already taken**, and the connection stays `AppNotCreated`. Remove it first, since `add --app-id` refuses a name that already exists:

    ```bash
    platform scm connection remove wasp-foundry
    ```

    Then either go in with **Existing App**, or delete the App (org **Settings → GitHub Apps → wasp-foundry-platform → Advanced → Delete GitHub App**) and run `add` through the browser again.
