# CLAUDE.md

## Handoff conventions

- **Task progress lives in GitHub Issues + the Project v2 board (#6, `smsilva/wasp-idp`), not in handoff files.** There is no `HANDOFF.local.md`. The board is the queue: its order is the position of each item (top first), and the next task is what is `In Progress`, else the top of `Todo`. `Todo` holds only what can start now; everything else waits in `Backlog`, also in order. `scripts/board/queue` reads and changes it (`next`, `list --status Todo`, `move <issue> --after <issue>`, `status <issue> Todo`): when a new issue enters, place it in the order, and when one closes, move the next one to `Todo`. Dependencies are written in the issue body. Each issue carries its own context, decisions and open questions in its body and comments. Split work into one issue per deliverable (sub-issues under a parent when they share a goal) and handle them in sequence, one branch and PR each. Before stopping mid-task, leave the state (last step, next step, open decision) as a comment on the issue — anything needed to resume on another machine must be on GitHub or in the repo, never only on local disk. Here, a handoff is that comment, and resuming starts from `scripts/board/queue next`.
- `HANDOFF.md` (root, versioned) keeps only broad repo state: what exists and is live, fronts delivered (one line + date), cross-cutting gotchas, pointers to ADRs/known-broken/board. Never task progress, and never the order of the work: that is the board's.

- PII (emails) and anything identifying a person/company go in `CLAUDE.local.md` (gitignored), never in `HANDOFF.md` — the repo is public.

- Completed-work narrative moves out of `HANDOFF.md` once a step is done, to keep it short. Keep only a one-line summary + date in `HANDOFF.md`. How the archive itself is organised (folder-per-theme, naming, immutability, `index.md` as the single entry point) is documented once, in `docs/archived/README.md` — read it there instead of restating the rule here.

- Backlog ("Next Steps") lives in GitHub Issues + Project v2 (board #6, `smsilva/wasp-idp`), not as a checklist in `HANDOFF.md`. Architecture decisions go to `docs/adr/` (Nygard format, one file per decision, immutable once accepted). Still-open findings/limitations and unresolved questions go to `aws/docs/known-broken.md` / `aws/docs/open-questions.md`; durable lessons already fixed but worth not relearning go to `aws/docs/lessons-learned/<topic>.md`. Client VPN operation (profile naming, connect/disconnect, troubleshooting) is documented once in `aws/docs/vpn/client-vpn-operations.md`. `HANDOFF.md` only points to these, never duplicates their content.

- **Every issue created must land on the board with `Status` set.** `gh issue create` does not add it (the board has no "Auto-add" workflow), and `gh project item-add` leaves `Status` empty, so the item lands in a "No Status" column the board view does not show.

  ```bash
  item_id="$(gh project item-add 6 --owner smsilva --url <issue-url> --format json --jq .id)"
  gh project item-edit --id "${item_id}" \
    --project-id PVT_kwHOAARkfs4Bh2xz \
    --field-id PVTSSF_lAHOAARkfs4Bh2xzzhgw8QM \
    --single-select-option-id 2841e349
  ```

  Confirm with `gh api graphql -f query='query{node(id:"<itemId>"){... on ProjectV2Item{fieldValueByName(name:"Status"){... on ProjectV2ItemFieldSingleSelectValue{name}}}}}'` — `item-list` lags minutes behind new items. `item-add` is idempotent, so re-running it is safe. Option ids: `Backlog` `2841e349`, `Todo` `1346028c`, `In Progress` `d9b40b84`, `Done` `1168c952`.

  Issues created outside a session (design conversations) often skip `item-add`: confirm membership per issue with GraphQL (`issue.projectItems`), since `item-list` lags behind.

  Audit now and then by diffing `gh issue list --state open --json number` against the `content.number` values from `gh project item-list` — pass `--limit 1000` to both, since `item-list` defaults to 30 items and a low limit silently truncates the newest items, which then look missing from the board.

- **`gh pr edit` / `gh issue edit` fail on this repo** with `GraphQL: Projects (classic) is being deprecated ... (repository.pullRequest.projectCards)`. The command exits non-zero and changes nothing — easy to read as "edited" if the output is not checked. Use the REST API instead: `gh api --method PATCH repos/smsilva/wasp-idp/pulls/<n> --input <file.json>` with `{"title": ..., "body": ...}`. `gh issue create`, `gh issue comment` and `gh issue close` are unaffected.

- **Closing keywords must be English** (`Closes #n`, `Fixes #n`). "Fecha #n" in a PR body does not close the issue on merge — close it by hand and move it to `Done` on the board.

- **Stacked PRs:** merging the base PR does not retarget the child (the base branch is not auto-deleted). Rebase the child with `git rebase --onto origin/main <base-commit>`, force-push, and switch its base to `main` via REST `{"base": "main"}`. GitHub may keep reporting `mergeable_state: dirty` after the retarget even with no real conflict; amending the commit (`--amend --no-edit --date=now`) and force-pushing forces a recompute.

- Write GitHub issue bodies so a fresh agent (no conversation context) can act without re-deriving facts already knowable from the code: state a checked fact directly ("the policy is already `Resource = \"*\"`"), never phrase it as "discover/verify whether X exists" when a `grep`/read already answers it. Phrased as a question, the fact sends the agent re-deriving what the author already knew.

## Branch naming

- Always create a branch when starting work on a GitHub issue. The branch name convention is: `feat/<issue_number>-<short-description>[-<phase-number>]`

## Platform CLI and Platform API

- `cli/` (package `wasp_platform`, script `platform`), `platform/api/`, `platform/libs/templates/` (package `wasp_templates`, the template renderer shared by CLI, API and the component creation controller) and each `platform/providers/*/` are separate `uv` projects: run `uv sync` and `uv run pytest` inside each. A project that depends on `platform/libs/*` by path builds its image with `platform/` as the context (`--file <project>/Dockerfile`), or the library is outside it. CLI docs: a walkthrough in `cli/docs/walkthrough/` (one step per page, the entry point) and a reference in `cli/docs/reference/` (one page per command group), published at `/cli/` by `.github/workflows/pages.yaml`. The MkDocs site is written in English (a pt-BR version is #274), unlike the rest of the repo docs.
- The repo has a single GitHub Pages site: `pages.yaml` builds the deck (root) and the CLI guide (`/cli/`) into one artifact. Add new sites as another build step there, never as a second deploy workflow — it would replace the whole site.
- The Platform API validates the Keycloak JWT on every `/v1/*` route (`platform/api/src/platform_api/auth.py`): `iss` is the public `http://localhost:8180/realms/platform` (KC_HOSTNAME) while the JWKS comes through the in-cluster Service. `TrustedHostMiddleware` (`127.0.0.1`/`localhost`) stays as defense in depth against DNS rebinding; keep the readiness probe sending `Host: localhost`.
- Keycloak's `platform-cli` client enforces PKCE, and Keycloak applies it to the device grant too: `--use-device-code` sends `code_challenge` on the device authorization request and `code_verifier` when polling.
- Environments are vclusters created by the `local_vcluster` controller inside `platform-local` (no host process). Each gets one host port from `7100`–`7119`: the range lives in both `ENV_PORTS` (`cli/src/wasp_platform/bootstrap/local.py`) and `PORTS` (`platform/providers/local_vcluster/src/local_vcluster_provider/reconciler.py`) — change both together.
- The status `kubeconfigData` is the vcluster admin certificate: it leaves the API only through `/admin-kubeconfig`, for `platform-admins`. `GET /v1/environments/{name}` returns a personal kubeconfig (an `exec` of `platform environment credential`, ADR 0028) only to `can_use`: the owner (annotation `platform.wasp.silvios.me/owner`, set from the token `sub` on create), `platform-admins`, or members of a team in `spec.sharedWith` (#232). Each person is a ServiceAccount named after their `sub` in the vcluster namespace `platform-identities`; unshare and team member removal delete it, which revokes its tokens. Never return kubeconfigs from list endpoints. Delete and share stay with `is_owner_or_admin` (#185).
- Cloud accounts (ADR 0029): the API never accepts `externalId` from the client and keeps it out of the journal; the `aws_account` provider is the only AWS caller and publishes the base identity in ConfigMap `aws-base-identity`, which is also what turns the `cloud-account` capability `Active`. Tests and docs use `123456789012`/`210987654321` only: the repo is public.
- Never restart Keycloak (theme reload, `platform init` with a changed theme) while someone is mid-login: the auth session lives in pod memory, and the Google callback hits a server that forgot it (`ERR_EMPTY_RESPONSE`).
- Every new CLI command or output change also updates the matching page in `cli/docs/walkthrough/` (and `cli/docs/reference/`) in the same change (#182).
- Catalog model (ADR 0023): Domain, System and shared Resource are CRDs in `catalog.platform.wasp.silvios.me`, owned by the Platform API; Component and API live in the repo `catalog-info.yaml`; a Resource used by only one app is derived from its Score by the Forager (the ADR 0022 resolver), never created by hand. A `ResourceRequest` is an instance per environment and never a catalog entity. Command shape is `platform catalog <kind> <verb>` (no `platform app …`); lifecycle commands take `--component`.
- Authorization reads group membership from the `group_paths` claim (full paths), never from the pathless `groups` claim: platform groups are the top-level paths (`/platform-admins`), teams are `/teams/<name>` (`Principal.teams`, ADR 0026). A homonym group elsewhere in the realm must grant nothing.
- Name validation in the API uses `re.fullmatch`: `re.match` with `$` accepts a trailing `\n`, which the kube API then rejects as a 500 with an unapplied journal entry.
- `scripts/demo/cli-smoke` runs the CLI flow without a browser (`platform login --test-user`/`--test-admin`, local target only, #179): run it to validate any CLI change, and add each new command's step to it. It uses its own `XDG_CONFIG_HOME`, so it never touches the real login.
- Tokens remember the client that issued them (`client_id` in the credentials file): refresh and revoke must go to that same client, or Keycloak refuses them.
- `platform catalog import` (#190) lives in `platform/api/src/platform_api/catalog_import.py`: the API computes the plan from raw Backstage documents, so every client gets the same plan. Skip reasons point to the issue that will import the kind (`Component`/`API` → #205); update them when that issue lands. Templates (#201) go through the same plan: `templates:import` is that route filtered to templates, so a template's owner team must already exist or come as a `Group` via `catalog import`.
- `platform catalog template render` fetches the registered `source.ref` from GitHub with git on the caller's machine: treat template content as untrusted (sandboxed Jinja2, no symlinks, https only, `--` before repo/ref). `platform init` registers the seed at the last commit present on the remote, so render works from an unpushed branch.
- The team-in-use check (`users_of` in `platform/api/src/platform_api/teams.py`) must list every kind with an `owner`: add each new owned kind there, or deleting its team orphans it.
- SCM connections (#199, ADR 0025): the GitHub App permissions live twice, `PERMISSIONS` in `platform/api/src/platform_api/scm.py` (the manifest) and `REQUIRED` in `platform/providers/scm_github/src/scm_github_provider/reconciler.py` (the check); a controller test fails when they differ. The API writes credentials through `SecretStore` and has no `get` on `secrets`: only the controller reads them. Journal records go through `redact()`.
- keycloak-config-cli manages `clients` fully (removes ones missing from the file) but never deletes `users`: removing a user from the realm file leaves it in Keycloak.

## IDP Tool (Backstage)

- See `docs/idp/CLAUDE.md` for the IDP Tool documentation. It is a separate document because it is long and detailed, and it is not part of the handoff itself.
