# Control plane

Write the settings once, with your Google e-mail as the admin (repeat `--admin` for more than one):

```bash
platform init \
  --generate-file \
  --admin you@example.com
```

Check what will be installed:

```bash
platform init --dry-run
```

Install:

```bash
time platform init
```

`init` reads `~/.config/platform/init.yaml`, shows each setting and where it came from, and asks before installing; `--yes` skips the question.

While it runs, a card shows the steps running now and the next ones, each with a bar that fills by its time in the last run (`--progress plain` prints one line per step instead). Each run keeps one log file per step; when a step fails, `init` shows the end of its file:

```bash
ls ~/.local/state/platform/init/latest/
```

The [reference](../../reference/init.md#logs) describes the files.
