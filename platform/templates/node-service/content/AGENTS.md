# AGENTS.md

`${{ values.name }}` is a Fastify service on Node.js created by the platform from the `node-service` template.

- Code in `src/`, tests in `test/` (`node:test`): run `npm test` before every commit.
- The home page is `src/page.js` (HTML in template literals, rendered by the server): every value from outside it goes through `escape()`. What this version does comes from `src/features.js`, so add an entry there with every endpoint you add, `new: true` while it is the change being shipped. Give new routes a `schema` with `tags`, `summary` and `response`: `/docs` (Swagger UI) is how people try them.
- `src/database.js` checks the database on every page load and on `GET /api/db`; `/healthz` never touches it, so a database outage does not restart the pod. Never put the password in a response or a log, and keep `SHOW_DATABASE_DETAILS` `"false"` outside demos: it shows the host, user and errors to anyone.
- `app-spec.yaml` (Score) declares what the service needs from each environment: add resources there, never hardcode hosts or credentials.
- Call other services with `fetch()`, from inside the request that needs them: `src/telemetry.js` passes the request's `baggage` and `traceparent` on to every call. The platform routes a sandbox by baggage (`sandbox=pr-42`), and one service that drops it sends every call after it to the stable versions. Never build those headers by hand, keep `require('./telemetry')` the first line of `src/app.js`, and keep the work of a request inside its async chain (no detached timers or queues without `context.with`).
- `catalog-info.yaml` is the catalog entry: keep `owner` and `description` current.
- Commit messages follow Conventional Commits (`feat:`, `fix:`, `feat!:`): they decide the next version.
- CI (`.github/workflows/ci.yaml`) tests every pull request and every push to `main`. Images come from `.github/workflows/platform-build.yaml`, which the platform dispatches: keep its file name, inputs and the `platform-build` artifact, they are the build contract.
