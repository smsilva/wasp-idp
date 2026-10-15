# List and get

A template is the **golden path** for a component type (ADR 0024). The content **stays in Git**; the platform keeps **only the record** (repo, path and ref). `platform init` registers the templates in `platform/templates/` at the checkout commit; the one marked `default: true` in its `template.yaml` (else the first of its type by name) becomes the default.

```bash
platform catalog template list

platform catalog template get python-service
```

``` { .text .output title="output" }
NAME                                          TYPE     REF                                       DEFAULT  SOURCE
node-service                                  service  38cee00afe1e9cbb25a3a4e89691728b4c7fb70c  —        https://github.com/smsilva/wasp-idp/platform/templates/node-service/content
python-service                                service  38cee00afe1e9cbb25a3a4e89691728b4c7fb70c  yes      https://github.com/smsilva/wasp-idp/platform/templates/python-service/content
python-service-with-postgresql-for-demo-only  service  38cee00afe1e9cbb25a3a4e89691728b4c7fb70c  —        https://github.com/smsilva/wasp-idp/platform/templates/python-service-with-postgresql-for-demo-only/content
template/python-service
  type         service
  default      yes
  repo         https://github.com/smsilva/wasp-idp
  path         platform/templates/python-service/content
  ref          38cee00afe1e9cbb25a3a4e89691728b4c7fb70c
  owner        team-platform
  description  FastAPI service with a home page, Swagger, a PostgreSQL check, CI to GHCR, Dockerfile and app-spec.yaml
  parameters
    port (integer, default 8000): Port the container listens on.
    theme (string, default indigo, one of indigo, teal, amber, rose): Accent color of the home page.
    title (string): Headline of the home page; the component name when not given.

next:

  platform catalog template render python-service \
    --name <component> \
    --output <folder>

  platform catalog component create <component> \
    --system <system> \
    --template python-service
```

`python-service-with-postgresql-for-demo-only` is the same template with `SHOW_DATABASE_DETAILS: "true"` in its `app-spec.yaml`: its home page and `/api/db` show the database host, user, server version and the driver's errors, which `python-service` keeps off the page (they go to the pod's log). The demos use it; a service people rely on uses `python-service`.

`node-service` is the same contract in Node.js (Fastify): the same routes, the same database panel and the same `title` parameter, with its own look so the two are told apart at a glance: a header band in the theme's color, with the Node.js and Fastify versions. Its `theme` takes `green` (the default), `lime`, `sky` or `violet`, and its `port` defaults to `3000`. Pick it with `--template node-service`; `python-service` stays the default for a `service`.
