# The connection in detail

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
