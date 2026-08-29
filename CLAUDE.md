# CLAUDE.md

## Handoff conventions

- `HANDOFF.md` (root) is the single, versioned session handoff — no `HANDOFF.local.md` counterpart. Never generate one; if it reappears, fold it into `HANDOFF.md` and delete it.

- PII (emails) and anything identifying a person/company go in `CLAUDE.local.md` (gitignored), never in `HANDOFF.md` — the repo is public.

- Completed-work narrative moves out of `HANDOFF.md` once a step is done, to keep the active handoff short. Keep only a one-line summary + date in `HANDOFF.md`. How the archive itself is organised (folder-per-theme, naming, immutability, `index.md` as the single entry point) is documented once, in `docs/archived/README.md` — read it there instead of restating the rule here.

- Backlog ("Next Steps") lives in GitHub Issues + Project v2 (board #6, `smsilva/wasp-idp`), not as a checklist in `HANDOFF.md`. Architecture decisions go to `docs/adr/` (Nygard format, one file per decision, immutable once accepted). Still-open findings/limitations and unresolved questions go to `aws/docs/known-broken.md` / `aws/docs/open-questions.md`; durable lessons already fixed but worth not relearning go to `aws/docs/lessons-learned/<topic>.md`. `HANDOFF.md` only points to these, never duplicates their content.

- Write GitHub issue bodies so a fresh agent (no conversation context) can act without re-deriving facts already knowable from the code: state a checked fact directly ("the policy is already `Resource = \"*\"`"), never phrase it as "discover/verify whether X exists" when a `grep`/read already answers it. That phrasing pattern caused real rework the first time it shipped — verified by dry-running a cold agent against the issue.

## IDP Tool (Backstage)

- See `docs/idp/CLAUDE.md` for the IDP Tool documentation. It is a separate document because it is long and detailed, and it is not part of the handoff itself.
