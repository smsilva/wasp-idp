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
