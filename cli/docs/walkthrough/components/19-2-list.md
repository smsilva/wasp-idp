# The component in the catalog

The component shows up in the catalog right after the create:

```bash
platform catalog component list \
  --system greeter

platform catalog component get greeting-api
```

``` { .text .output title="output" }
NAME          SYSTEM   OWNER       LIFECYCLE     TEMPLATE
greeting-api  greeter  team-alpha  experimental  python-service@0b81690231edcd5920c1f774efc0325c80a4b0a4
component/greeting-api
  system       greeter
  owner        team-alpha
  type         service
  lifecycle    experimental
  repo         wasp-foundry/greeting-api
  template     python-service@0b81690231edcd5920c1f774efc0325c80a4b0a4
  description  —
```

The repo has a single commit, and its `catalog-info.yaml` carries where it came from:

```bash
gh api repos/wasp-foundry/greeting-api/contents/catalog-info.yaml \
  --jq .content | base64 --decode | grep --extended-regexp 'template:|project-slug:'
```

``` { .text .output title="output" }
    platform.wasp.silvios.me/template: python-service@0b81690231edcd5920c1f774efc0325c80a4b0a4
    github.com/project-slug: wasp-foundry/greeting-api
```

!!! note
    The catalog entry is a **read mirror** of that `catalog-info.yaml` (ADR 0023): changing the component is a pull request in its repo, never a CLI command.
