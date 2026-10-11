---
name: next
description: Use when the user asks to pick up, resume, or start the next issue of the wasp-idp board ("next", "próxima issue", "pegue a próxima issue do board"), or names an issue number to work on. Loads the issue context and presents the design before any implementation.
argument-hint: "[issue-number]"
---

# Next issue from the board

The board (Project v2 #6, `smsilva/wasp-idp`) is the work queue. Its order is the item position, top first. This skill loads one issue and stops at a design for the user to approve.

## Steps

1. **Pick the issue.** With an argument, use that issue number. Without one, run `scripts/board/queue next`: an `In Progress` item wins over the top of `Todo`. If both are empty, show `scripts/board/queue list --status Backlog | head` and ask which one to promote.

2. **Read the whole issue.** `gh issue view <n> --comments` omits the body, so run both:

   ```bash
   gh issue view <n> --json title,body,labels --jq '.title, .body'
   gh issue view <n> --comments
   ```

   The last comment is often a handoff (last step, next step, open decision): resume from it.

3. **Check the dependencies** listed in the body: each one is closed (`gh issue view <dep> --json state`) or the code it delivers is on `main`. If one is missing, report it and stop.

4. **Check existing work.** Look for a branch and a PR:

   ```bash
   git branch --all --list "*<n>-*"
   gh pr list --state all --search "<n> in:title"
   ```

   A branch with commits ahead of `main` means resume, not restart.

5. **Read what the issue points to:** ADRs in `docs/adr/`, specs in `docs/superpowers/specs/`, and the code paths it names. Read before you design: state checked facts, never "verify whether".

6. **Present the design and stop.** Reply in pt-BR with:
   - one line on the issue and its state (new, resuming, blocked);
   - the cut: one PR, or sub-issues (one per deliverable) when the scope spans several;
   - per deliverable: CRDs, API routes, controller, CLI, docs (`cli/docs/walkthrough/`, `cli/docs/reference/`) and the `scripts/demo/cli-smoke` step;
   - open decisions, each with a recommendation.

   Do not write code, create branches, or change the board before the user approves.

## After approval

- Create sub-issues when the design splits the work, and put each on the board with `Status` set (see `CLAUDE.md`).
- Set the issue to `In Progress` with `scripts/board/queue status <n> "In Progress"`.
- Branch from `main`: `feat/<n>-<short-description>`.
- Before stopping mid-task, leave a handoff comment on the issue (last step, next step, open decision).
- When the issue closes, move the next item to `Todo` (`scripts/board/queue status <next> Todo`).
