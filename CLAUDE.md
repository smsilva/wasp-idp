# CLAUDE.md

## Handoff conventions

- `HANDOFF.md` (root) is the single, versioned session handoff — no `HANDOFF.local.md` counterpart. Never generate one; if it reappears, fold it into `HANDOFF.md` and delete it.

- PII (emails) and anything identifying a person/company go in `CLAUDE.local.md` (gitignored), never in `HANDOFF.md` — the repo is public.

- Completed-work narrative moves out of `HANDOFF.md` once a step is done, to keep the active handoff short. Keep only a one-line summary + date in `HANDOFF.md`. How the archive itself is organised (folder-per-theme, naming, immutability, `index.md` as the single entry point) is documented once, in `docs/archived/README.md` — read it there instead of restating the rule here.

- Backlog ("Next Steps") lives in GitHub Issues + Project v2 (board #6, `smsilva/wasp-idp`), not as a checklist in `HANDOFF.md`. Architecture decisions go to `docs/adr/` (Nygard format, one file per decision, immutable once accepted). Still-open findings/limitations and unresolved questions go to `aws/docs/known-broken.md` / `aws/docs/open-questions.md`; durable lessons already fixed but worth not relearning go to `aws/docs/lessons-learned/<topic>.md`. `HANDOFF.md` only points to these, never duplicates their content.

- **Every issue created must land on the board — in two steps, not one.** `gh issue create` does NOT add it: the board has no "Auto-add" workflow, so the issue is born outside it and that backlog is invisible (it happened to #38, #39, #56, #62, #64, #65). And adding is not enough — `gh project item-add` leaves `Status` empty, and the board view groups by `Status`, so a valueless item lands in a "No Status" column nobody looks at.

  ```bash
  gh project item-add 6 --owner smsilva --url <issue-url>
  gh project item-list 6 --owner smsilva --format json   # to get the itemId
  gh project item-edit --id <itemId> \
    --project-id PVT_kwHOAARkfs4Bh2xz \
    --field-id PVTSSF_lAHOAARkfs4Bh2xzzhgw8QM \
    --single-select-option-id 2841e349
  ```

  Option ids: `Backlog` `2841e349`, `Todo` `1346028c`, `In Progress` `d9b40b84`, `Done` `1168c952`. Audit now and then by diffing `gh issue list --state open --json number` against the `content.number` values from `item-list` — an open issue off the board is work lost from sight. **Pass `--limit 100` to both:** `item-list` defaults to 30 items and the board already has more than that, so the default silently omits items and an audit run without it reports issues as "missing from the board" that are already on it. `item-add` is idempotent — calling it twice does not duplicate the item, so re-running after an unclear result is safe.

- **`gh pr edit` / `gh issue edit` fail on this repo** with `GraphQL: Projects (classic) is being deprecated ... (repository.pullRequest.projectCards)`. The command exits non-zero and changes nothing — easy to read as "edited" if the output is not checked. Use the REST API instead: `gh api --method PATCH repos/smsilva/wasp-idp/pulls/<n> --input <file.json>` with `{"title": ..., "body": ...}`. `gh issue create`, `gh issue comment` and `gh issue close` are unaffected.

- Write GitHub issue bodies so a fresh agent (no conversation context) can act without re-deriving facts already knowable from the code: state a checked fact directly ("the policy is already `Resource = \"*\"`"), never phrase it as "discover/verify whether X exists" when a `grep`/read already answers it. That phrasing pattern caused real rework the first time it shipped — verified by dry-running a cold agent against the issue.

## Branch naming

- Always create a branch when starting work on a GitHub issue. The branch name convention is: `feat/<issue_number>-<short-description>[-<phase-number>]`

## IDP Tool (Backstage)

- See `docs/idp/CLAUDE.md` for the IDP Tool documentation. It is a separate document because it is long and detailed, and it is not part of the handoff itself.
