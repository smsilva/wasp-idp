# Control plane

Write the settings once, with your Google e-mail as the admin:

```bash
platform init \
  --generate-file \
  --admin you@example.com
```

See what will be installed:

```bash
platform init --dry-run
```

Install, after confirming the settings:

```bash
time platform init
```
