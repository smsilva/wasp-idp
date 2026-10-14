# Walkthrough review session

Saved 2026-10-14 on branch `walkthrough`, in `/home/silvios/git/wasp-idp` (main checkout).

The user runs the CLI walkthrough step by step and comes back now and then ("oi", "olhe"). Infer where they are and report it. Reply in pt-BR.

## Setup

- Commands run in tmux pane `0:1.0`.
- The guide page is open in Chrome, on the left half of the primary monitor, served at `http://127.0.0.1:8000/wasp-idp/cli/walkthrough/...`.
- Page order: the `nav` of `cli/mkdocs.yml`; page content: `cli/docs/walkthrough/`.

## Each time the user checks in

1. Capture the pane: `tmux capture-pane -p -t 0:1.0 -S -80`.
2. Screenshot the primary monitor, found each time (the setup changes), and read it:

   ```bash
   read -r w h x y < <(xrandr --query | awk '/ connected primary/ {print $4}' | tr 'x+' '  ')
   scrot -a "${x},${y},${w},${h}" /tmp/peek/walkthrough/<NNN>_primary.png
   ```

   NNN is zero-padded and goes up by one each time.
3. Match the commands in the pane and the page in the browser against `cli/docs/walkthrough/`.
4. Report briefly: the current page, the **last command run** and its result, any error, and the next page.

## Problems found

When a step fails or reads wrong (an error on a clean machine, noise in generated output), note it, propose the fix, and implement it when the user says so.

## Commits

Commit on the current branch, one commit per change, and push after every commit.

## Standing instructions

When the user gives an instruction meant to outlast this session (how to look, what to report, how to commit), offer `/next save` so it reaches this file before the next `/clear`.

## Start

There is no memory of earlier sessions: earlier fixes are already in the repo. Open with one line, "prompt local carregado: revisão do walkthrough, branch `<branch>`", then look at the pane and the screen and report where the user is.
