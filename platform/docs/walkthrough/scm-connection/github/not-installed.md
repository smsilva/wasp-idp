# Until the App is installed

Without the installation, the connection stays `NotInstalled`. `get` shows the link to install it:

```bash
platform scm connection get wasp-foundry
```

``` { .text .output title="output" }
wasp-foundry (default): NotInstalled
  the App wasp-foundry-platform is not installed on wasp-foundry: https://github.com/apps/wasp-foundry-platform/installations/new
  vendor:       github
  org:          wasp-foundry
  app:          wasp-foundry-platform (id 5274859)
  install:      https://github.com/apps/wasp-foundry-platform/installations/new
```
