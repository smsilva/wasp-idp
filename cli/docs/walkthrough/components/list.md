# The component in the catalog

The component shows up in the catalog right after the create:

```bash
platform catalog component list \
  --system greeter

platform catalog component get hello-api
```

``` { .text .output title="output" }
NAME       SYSTEM   OWNER       LIFECYCLE     TEMPLATE
hello-api  greeter  team-alpha  experimental  python-service@5adb796c62a44bb2b580dda4ef7d21d49ae82ba9
component/hello-api
  system       greeter
  owner        team-alpha
  type         service
  lifecycle    experimental
  repo         wasp-foundry/hello-api
  template     python-service@5adb796c62a44bb2b580dda4ef7d21d49ae82ba9
  description  —
  running in   —
```

The repo has a single commit (the README of `auto_init` is replaced), and its `catalog-info.yaml` carries where it came from:

```bash
gh api repos/wasp-foundry/hello-api/contents/catalog-info.yaml \
  --jq .content \
  | base64 --decode \
  | grep --extended-regexp 'template:|project-slug:'
```

``` { .text .output title="output" }
    platform.wasp.silvios.me/template: python-service@5adb796c62a44bb2b580dda4ef7d21d49ae82ba9
    github.com/project-slug: wasp-foundry/hello-api
```

!!! note
    The catalog entry is a **read mirror** of that `catalog-info.yaml` (ADR 0023): changing the component is a pull request in its repo, never a CLI command.
