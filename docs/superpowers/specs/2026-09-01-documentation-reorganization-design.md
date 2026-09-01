# Documentation reorganization — design

Brainstorming spec for [#64](https://github.com/smsilva/wasp-idp/issues/64). Covers the structure
proposal only — the first deliverable the issue asks for, before any `git mv`.

## Context

251 versioned `.md` files outside `idp/`, grown by accretion across phases. No navigation path
lets someone — human or agent — arrive without context and find what they need. Two documentation
trunks exist with different cutoff criteria: `aws/docs/` (Well-Architected reference by domain) and
`docs/` (ADRs, archived narrative, superpowers process artifacts, idp). The root `README.md` covers
only Backstage and never mentions AWS, so there is no entry point for most of the repo's content.

Concrete symptom that triggered this issue: during #52, `aws/terraform/github/README.md` was
written from scratch because `aws/terraform/ci/README.md` already covered half the topic — the
root `ci/` was missing from the "Raízes" table in `aws/terraform/README.md`, so there was no
navigation path to it. Fixed locally in #63; the same failure mode will recur elsewhere without a
structural fix.

Full numbers and the six open tensions are in the issue body; this spec resolves each tension with
a decision rather than restating the question.

## Decision: minimal consolidation (Approach A)

Both physical trunks (`aws/docs/` by domain, `docs/` for adr/archived/idp) stay where they are.
Domain folders under `aws/docs/` do not move. The fix is entry points and role separation, not a
mass `git mv` — this keeps blast radius low and avoids the exact risk the issue calls out: breaking
links that work today by reorganizing with the wrong taxonomy.

Two other approaches were considered and rejected:

- **Unify by lifecycle** (`docs/{reference,decisions,archived,process}/`, folding `aws/docs/` in)
  — resolves the two-trunk duplication for good, but requires renaming/moving hundreds of files at
  once, which is the risk this issue explicitly wants to avoid on the first pass.
- **Map only, zero physical movement** — lowest risk, but leaves the concrete symptom (missing
  entry points) unfixed; deferred as a possible follow-up, not chosen because the fixes below are
  small enough to do now.

## Navigation structure

```
README.md (root)                    ← rewritten: real entry point
  ├── link → docs/idp/               (Backstage — current README content moves here)
  ├── link → aws/docs/CLAUDE.md      (AWS reference architecture)
  ├── link → aws/terraform/README.md (how to provision)
  ├── link → docs/adr/README.md      (decisions)
  └── link → docs/archived/README.md (delivery history)

aws/docs/                           ← physically unchanged; gains README.md
  <domain>/CLAUDE.md                ← domain rules/conventions (stays)
  <domain>/README.md                ← NEW: domain's navigable index

docs/adr/          (already good, no change)
docs/archived/     (already good, no change)
docs/idp/          (becomes the Backstage entry point)

docs/superpowers/{specs,plans}/     ← drops out of the read index; gains its
                                       own README.md stating it is process
                                       memory, not reference — not moved
                                       physically for now
```

This is the entry-point layer the repo is missing today. `aws/terraform/README.md`'s existing
"Raízes" table is the precedent this generalizes from — the root `README.md` becomes the
master table pointing into it and the other trunks.

## `CLAUDE.md` / `README.md` role split

Resolves tension 1. Every `CLAUDE.md` that today doubles as a folder index (11 of 14) gets a
sibling `README.md`.

- **`README.md`** = navigation: what's here, what it's for, when to read each file. Serves humans
  and agents alike; this is what MkDocs `navigation.indexes` will expect for the follow-up site
  issue.
- **`CLAUDE.md`** = imperative instruction for the agent: conventions to follow, maintenance rules
  ("keep this file true"), known pitfalls. Does not repeat the README's index.

Where only `CLAUDE.md` exists today, its index content moves into a new `README.md`; what remains
in `CLAUDE.md` is rules only. Where only `README.md` exists and mixes index with rules (e.g.
`aws/terraform/README.md`, which has a "Manter este arquivo verdadeiro" section), the rules move
into a new `CLAUDE.md`.

## One-topic-per-document rule

Resolves tension 3. A document covers one subject. When a section starts going deep into a
sub-topic that deserves its own treatment, it becomes a separate file, referenced from where it
made sense — following the precedent of the `2026-08-29-regional-root-hub-and-cell-modules/` split
into four numbered files. No fixed line-count threshold; the seven large files the issue lists
(2035 down to ~440 lines) are split candidates, not an automatic mandatory split — whoever edits a
file decides, by checking whether it already covers more than one subject. Applies to new content
going forward, not just the existing large files.

## `docs/superpowers/{specs,plans}/` out of the main index

Resolves tension 2. Gains its own `README.md` stating it is process memory (how a decision was
made), not reference documentation — and for that reason does not appear in the repo root's read
index or in `aws/docs/CLAUDE.md`. Not moved physically, consistent with the minimal-consolidation
approach. If the future MkDocs site issue needs to exclude this tree from `nav:`, the README makes
that explicit already.

## Link verification

New script `scripts/bin/check-doc-links` (no extension, per this repo's `bash-scripts` convention),
run manually at the end of the reorganization's execution step. Scans `git ls-files` with no
extension filter (the rule already in force in `aws/docs/CLAUDE.md`) for relative references that
don't resolve. Left in the repo for future reuse; not wired into CI now.

## Scope

**In scope for this issue's execution step:**
- Root `README.md` rewrite (entry point).
- `CLAUDE.md`/`README.md` split for the `CLAUDE.md` files that function as a folder index (11 of
  the 14 existing) and for `aws/terraform/README.md`, which mixes index with rules the other way
  around.
- New `docs/superpowers/README.md` marking that tree as process memory.
- `scripts/bin/check-doc-links`, run against the files this issue touches.
- ADR recording this decision.

**Out of scope, explicitly:**
- Known PII leaks (account id, email) in generic docs — stays on #23, not touched here.
- Physical reorganization of `aws/docs/` domain folders or `docs/superpowers/` — no `git mv` of
  existing reference content beyond what's listed above. A future issue can revisit specific
  folders if a real need appears.
- Wiring `check-doc-links` into CI.

## Maintenance rule placement

Per the repo's own convention, files that already carry a "Manter este arquivo verdadeiro" table
get the corresponding line added once this structure lands (e.g. `aws/docs/CLAUDE.md`,
`docs/archived/README.md`, the new root `README.md`).
