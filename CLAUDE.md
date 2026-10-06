# CLAUDE.md

## Handoff conventions

- Two handoff files, split by scope:
  - `HANDOFF.local.md` (root, gitignored) — task progress: the active front, last step, next step, state of the local environment (clusters, running processes). Every in-flight task lives here.
  - `HANDOFF.md` (root, versioned) — broad, general state of the repo: what exists and is live, fronts delivered (one line + date), cross-cutting gotchas, pointers to ADRs/known-broken/board. Never task progress ("parado em", "próximo passo" of a specific task).

- PII (emails) and anything identifying a person/company go in `CLAUDE.local.md` (gitignored), never in `HANDOFF.md` — the repo is public.

- Completed-work narrative moves out of `HANDOFF.md` once a step is done, to keep the active handoff short. Keep only a one-line summary + date in `HANDOFF.md`. How the archive itself is organised (folder-per-theme, naming, immutability, `index.md` as the single entry point) is documented once, in `docs/archived/README.md` — read it there instead of restating the rule here.

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

  Audit now and then by diffing `gh issue list --state open --json number` against the `content.number` values from `gh project item-list` — pass `--limit 100` to both, since `item-list` defaults to 30 items and the board has more.

- **`gh pr edit` / `gh issue edit` fail on this repo** with `GraphQL: Projects (classic) is being deprecated ... (repository.pullRequest.projectCards)`. The command exits non-zero and changes nothing — easy to read as "edited" if the output is not checked. Use the REST API instead: `gh api --method PATCH repos/smsilva/wasp-idp/pulls/<n> --input <file.json>` with `{"title": ..., "body": ...}`. `gh issue create`, `gh issue comment` and `gh issue close` are unaffected.

- Write GitHub issue bodies so a fresh agent (no conversation context) can act without re-deriving facts already knowable from the code: state a checked fact directly ("the policy is already `Resource = \"*\"`"), never phrase it as "discover/verify whether X exists" when a `grep`/read already answers it. That phrasing pattern caused real rework the first time it shipped — verified by dry-running a cold agent against the issue.

## Branch naming

- Always create a branch when starting work on a GitHub issue. The branch name convention is: `feat/<issue_number>-<short-description>[-<phase-number>]`

## IDP Tool (Backstage)

- See `docs/idp/CLAUDE.md` for the IDP Tool documentation. It is a separate document because it is long and detailed, and it is not part of the handoff itself.
