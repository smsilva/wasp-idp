# Verify

After the installation, GitHub returns to the "App installed" page, which **already requests the verification**:

![Platform API "App installed" page, which already requested the verification](../images/scm-04-app-installed.png){ .screenshot loading=lazy width="500" }

```bash
platform scm connection verify wasp-foundry \
  --wait

platform scm connection list
```

``` { .text .output title="output" }
✓ wasp-foundry ready (wasp-foundry, all repositories)
→ register its GHCR, where builds of wasp-foundry repos push: platform registry add ghcr-wasp-foundry --scm-connection wasp-foundry --default
NAME          VENDOR  ORG           STATUS  DEFAULT  VALIDATED
wasp-foundry  github  wasp-foundry  ready   yes      2026-10-11T14:52:26Z
```

`get` shows the installation and the checked permissions:

```bash
platform scm connection get wasp-foundry
```

``` { .text .output title="output" }
wasp-foundry (default): ready
  the App is installed on every repository of the org with the permissions it needs
  vendor:       github
  org:          wasp-foundry
  app:          wasp-foundry-platform (id 5274859)
  installation: 170292387
  repositories: all
  permissions:  actions:write, administration:write, contents:write, metadata:read, pull_requests:write, workflows:write
  validated:    2026-10-11T14:52:26Z
```

| Status | What to do | `verify --wait` |
|---|---|---|
| `AppNotCreated` | run `add` again | — |
| `NotInstalled` | install the App via the `installUrl` from `get` | waits |
| `NotAllRepositories` | switch the installation to All repositories | stops |
| `MissingPermissions` | update the App and accept it on the org (the message lists what is missing) | stops |
| `ready` | nothing; the controller revalidates every 6 h | finishes |
