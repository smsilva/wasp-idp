# CLAUDE.md

## Handoff conventions

- `HANDOFF.md` (root) is the single, versioned session handoff — no `HANDOFF.local.md` counterpart. Never generate one; if it reappears, fold it into `HANDOFF.md` and delete it.

- PII (emails) and anything identifying a person/company go in `CLAUDE.local.md` (gitignored), never in `HANDOFF.md` — the repo is public.

- Completed-work narrative moves out of `HANDOFF.md` once a step is done, to keep the active handoff short. Keep only a one-line summary + date in `HANDOFF.md`. How the archive itself is organised (folder-per-theme, naming, immutability, `index.md` as the single entry point) is documented once, in `docs/archived/README.md` — read it there instead of restating the rule here.

## IDP Tool (Backstage)

- See `docs/idp/CLAUDE.md` for the IDP Tool documentation. It is a separate document because it is long and detailed, and it is not part of the handoff itself.
