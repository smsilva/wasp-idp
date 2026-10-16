# The component in the catalog

The component shows up in the catalog right after the create:

```bash
platform catalog component list \
  --system seat-map

platform catalog component get seat-selection
```

``` { .text .output title="output" }
NAME            SYSTEM    OWNER       LIFECYCLE     TEMPLATE
seat-selection  seat-map  team-alpha  experimental  python-service@5adb796c62a44bb2b580dda4ef7d21d49ae82ba9
component/seat-selection
  system       seat-map
  owner        team-alpha
  type         service
  lifecycle    experimental
  repo         wasp-foundry/seat-selection
  template     python-service@5adb796c62a44bb2b580dda4ef7d21d49ae82ba9
  description  —
  creation     ready, 2m ago
  builds       —
  versions     —
  running in   —

next:

  platform build list \
    --component seat-selection

  platform workload list \
    --component seat-selection

  platform catalog component creation get seat-selection

  platform catalog component clone seat-selection
```

- `get` also shows what the component generated: its creation (only to you, who requested it, and to `platform-admins`, for 24 h after it ends), its newest build and version, and where it runs. Nothing is built nor deployed yet, so those lines are `—`; `--hide-empty` leaves them out.
- `next:` lists the commands that follow from here, with the component's name already in them. It goes to stderr, so `platform catalog component get seat-selection | grep repo` gets only the table.

The repo has a single commit (the README of `auto_init` is replaced), and its `catalog-info.yaml` carries where it came from:

```bash
gh api repos/wasp-foundry/seat-selection/contents/catalog-info.yaml \
  --jq .content \
  | base64 --decode \
  | grep --extended-regexp 'template:|project-slug:'
```

``` { .text .output title="output" }
    platform.wasp.silvios.me/template: python-service@5adb796c62a44bb2b580dda4ef7d21d49ae82ba9
    github.com/project-slug: wasp-foundry/seat-selection
```

!!! note
    The catalog entry is a **read mirror** of that `catalog-info.yaml` (ADR 0023): changing the component is a pull request in its repo, never a CLI command.
