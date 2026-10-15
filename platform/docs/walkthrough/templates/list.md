# List and get

A template is the **golden path** for a component type (ADR 0024). The content **stays in Git**; the platform keeps **only the record** (repo, path and ref). `platform init` registers the templates in `platform/templates/` at the checkout commit, and the first of each type becomes the default.

```bash
platform catalog template list

platform catalog template get python-service
```

``` { .text .output title="output" }
NAME            TYPE     REF                                       DEFAULT  SOURCE
python-service  service  0b81690231edcd5920c1f774efc0325c80a4b0a4  yes      https://github.com/smsilva/wasp-idp/platform/templates/python-service/content
template/python-service
  type         service
  default      yes
  repo         https://github.com/smsilva/wasp-idp
  path         platform/templates/python-service/content
  ref          0b81690231edcd5920c1f774efc0325c80a4b0a4
  owner        team-platform
  description  FastAPI service with CI to GHCR, Dockerfile and app-spec.yaml
  parameters
    port (integer, default 8000): Port the container listens on.

next:

  platform catalog template render python-service \
    --name <component> \
    --output <folder>

  platform catalog component create <component> \
    --system <system> \
    --template python-service
```
