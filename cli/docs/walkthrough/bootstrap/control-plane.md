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

Install, after confirming the settings:

```bash
platform init
```
