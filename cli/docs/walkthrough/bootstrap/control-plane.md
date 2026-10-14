# Control plane

Write the settings once, with your e-mail as the admin:

```bash
platform init \
  --generate-file \
  --admin you@example.com
```

Repeat `--admin` for more than one admin.
{ .terminal-note }

See what will be installed:

```bash
platform init --dry-run
```

Change a setting with `platform init --edit`: it opens the file in `$PLATFORM_EDITOR`, `$VISUAL` or `$EDITOR`, else VS Code.
{ .terminal-note }

Install, after confirming the settings:

```bash
platform init
```
