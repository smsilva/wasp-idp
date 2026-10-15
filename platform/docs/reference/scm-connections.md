# SCM connections

A connection tells the platform which org to create repos in and with which credential (ADR 0025). In this slice, GitHub only. Only `platform-admins` manage connections.

| Command | What it does |
|---|---|
| `platform scm connection add <name> --vendor github --org <org> [--default] [--wait]` | creates the `<org>-platform` GitHub App through the manifest flow, in the browser |
| `… add <name> --vendor github --org <org> --no-browser` | prints the manifest flow URL instead of opening the browser |
| `… add <name> --vendor github --org <org> --app-id <id> --private-key-file <pem>` | uses an App that already exists, without a browser |
| `platform scm connection list` | NAME, VENDOR, ORG, STATUS, DEFAULT, VALIDATED |
| `platform scm connection get <name>` | status, App, installation, permissions and the install link |
| `platform scm connection verify <name> [--wait]` | asks the controller to check the App and its installation again |
| `platform scm connection default <name>` | the connection used when none is named |
| `platform scm connection remove <name>` | deletes the connection and the key; the App stays on GitHub, and the output says where to delete it |

`get` takes `--hide-empty` (the table never shows empty fields, so it changes only a data output). Its `next:` footer is `verify --wait` until the connection is `ready`; then `registry add` for the org's GHCR while no registry has it, `default` when it is not the default, and `component create` ([After a `get`](output.md#after-a-get)).

## Manifest flow

- Whoever confirms on GitHub must be an owner of the org.
- The URL is single-use and valid for 10 minutes; it lives in the memory of the API, so restarting the API means running `add` again.
- GitHub returns the private key straight to the platform, which stores it in a Secret the API cannot read; only the controller reads it. The key never reaches your machine nor the journal.
- The App asks for `administration`, `contents`, `workflows`, `pull_requests` and `actions` with write, and `metadata` read; it is private and has no webhook.

## Status

| Status | What to do | `verify --wait` |
|---|---|---|
| `AppNotCreated` | run `add` again | — |
| `NotInstalled` | install the App on the org through the link from `get` | waits |
| `NotAllRepositories` | switch the installation to All repositories | stops |
| `MissingPermissions` | update the App and accept on the org (the message lists what is missing) | stops |
| `ready` | nothing; the controller revalidates every 6 h | ends |
