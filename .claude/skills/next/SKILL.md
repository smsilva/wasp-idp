---
name: next
description: Use when the user asks to pick up, resume, or start the next issue of the wasp-idp board ("next", "próxima issue", "pegue a próxima issue do board", "pega uma nova", "quero algo de AWS", "o que o time está fazendo"), or names an issue number to work on. The user types short words (`new`, `track aws`, `team`) or free phrases, never flags. Claims the issue (assignee + In Progress), loads its context and presents the design before any implementation. When .claude/PROMPT.local.md has content, follows that session prompt instead; "save" writes it from the current session, "clear" archives it to ~/.claude/prompts/ and removes it.
argument-hint: "[number | new | track <value> | theme <value> | team | save | clear]"
---

# Next issue from the board

The board (Project v2 #6, `smsilva/wasp-idp`) is the work queue, shared by a team working in parallel. Its order is the item position, top first. "Me" is the active `gh` account (`gh api user --jq .login`). An issue someone else holds is never mine. This skill loads one issue and stops at a design for the user to approve.

## Session prompt

`.claude/PROMPT.local.md` (gitignored) is a session prompt: the instructions the user gave in an earlier session, so `/clear` followed by `/next` resumes the same way of working. It carries no memory of what was done: the work itself is in the repo. An empty file counts as missing.

- **No argument, the file has content:** read it and follow it in place of the steps below. Skip the board. If the current branch or checkout path differs from the header, say so and ask before the first commit.
- **No argument, the file is missing:** run the steps below (the board).
- **`save`:** draft the prompt from the current session (in English, imperative, to a fresh agent: the context, each standing instruction, the start; drop what was done). Record the date, the branch and the checkout path (a worktree's own path, or the main checkout) in the header. When the file exists, merge into it and show the diff; else show the draft in full. Write only after the user confirms, then show its absolute path and tell them they can run `/clear` and then `/next`.
- **`clear`:** show the file, then archive it before removing: copy it to `~/.claude/prompts/wasp-idp/<topic>.md`, where `<topic>` names the theme it covers in lowercase-hyphenated words (`walkthrough-review.md`); when that name exists, add a date suffix (`walkthrough-review-2026-10-14.md`). Confirm the copy with `cmp`, show its absolute path, then remove the original with `rm` (never leave it empty) only after the user confirms. `/next` goes back to the board.

## Steps

1. **Pick the issue.**

   - **With an issue number:** use it, unless `gh issue view <n> --json assignees` shows someone else. Then refuse and say who holds it; go on only if the user says it is a takeover.
   - **Without one:** run `scripts/board/queue next`. It lists my own `In Progress` items; with none, it shows the top of `Todo` that has no assignee, no open sub-issues and no `feat/<n>-*` branch on origin. An issue with open sub-issues is skipped (the parent stays `In Progress` while its sub-issues are the work). With two or more of my own items, list them and ask which one to resume.
   - **The user types a word from this vocabulary; you run the matching `queue` command** (the user never types the `--` flags):

     | Word | Meaning | You run |
     | --- | --- | --- |
     | *(none)* | resume my item, else claim the top free `Todo` | `queue next` |
     | `new` | a new item even with one open (no WIP limit, the user's call) | `queue next --new` |
     | `track <value>` | a new item of that `Track` (asking for an area means a new item, so it implies `new`) | `queue next --new --track <value>` |
     | `theme <value>` | a new item of that `Theme` (implies `new`) | `queue next --new --theme <value>` |
     | `team` | who is on what, claims nothing | `queue team` |
     | `<number>` | that issue | the "With an issue number" rule above |

     A free phrase ("pega uma nova", "quero algo de AWS", "o que o time está fazendo") stays valid: read it as the closest word. The vocabulary fixes the action, never the value: for `<value>` ignore case, and when the words match no `Track`/`Theme` exactly, or match several (`docs` is `CLI docs` or `Architecture docs`), run `queue next --new --theme x` to get the values in use (the script prints them on an unknown value) and ask which one.
   - With several candidates and no filter, prefer the `Theme` of the last issue I closed.
   - **Claim before anything else:** for a `Todo` candidate run `scripts/board/queue claim <n>`. It assigns me and sets `In Progress`; if it refuses (someone else holds it or claimed at the same moment), run `queue next` again. A resumed item of mine needs no claim.
   - If any `queue` command fails with `the gh token of <login> lacks the 'project' scope` or `<login> cannot see board #6`, relay the message and its fix to the user and stop: do not try to work around it (no other account, no direct GraphQL).
   - If `queue next` prints a `warning: N In Progress without assignee` line, pass it on to the user and mention `scripts/board/queue doctor`. Do not take an orphan.
   - If both are empty, show `scripts/board/queue list --status Backlog | head` and ask which one to promote.

2. **Read the whole issue.** `gh issue view <n> --comments` omits the body, so run both:

   ```bash
   gh issue view <n> --json title,body,labels --jq '.title, .body'
   gh issue view <n> --comments
   ```

   The last comment is often a handoff (last step, next step, open decision): resume from it.

   A sub-issue carries only its cut and the decisions taken; the full scope and acceptance criteria live in the parent. Read the parent the same way (`gh issue view <n> --json parent --jq .parent.number`).

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
   - the team panel from `scripts/board/queue team` (who is on what, with the `Theme` of each): flag a `Theme` shared with someone else as a merge-conflict risk, without skipping the issue;
   - the cut: one PR, or sub-issues (one per deliverable) when the scope spans several;
   - per deliverable: CRDs, API routes, controller, CLI, docs (`platform/docs/walkthrough/`, `platform/docs/reference/`) and its step in `scripts/test/cli-smoke` (control plane) or `scripts/test/cli-e2e` (needs an environment);
   - open decisions, each with a recommendation.

   Do not write code, create branches, or change the board before the user approves.

## After approval

- Create sub-issues when the design splits the work, and put each on the board with `Status` set (see `CLAUDE.md`).
- The issue is already assigned to me and `In Progress` from the claim. To give it up, run `scripts/board/queue release <n>`.
- Branch from `main`: `feat/<n>-<short-description>`.
- Before stopping mid-task, leave a handoff comment on the issue (last step, next step, open decision).
- When the issue closes, move the next item to `Todo` (`scripts/board/queue status <next> Todo`).
