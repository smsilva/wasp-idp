# A new default

**One default per type:** marking another unmarks the previous one, and the default only goes away after another takes over.

```bash
platform catalog template create go-service \
  --type service \
  --owner team-platform \
  --repo https://github.com/smsilva/wasp-idp \
  --path platform/templates/python-service/content \
  --ref main

platform catalog template default go-service
```

``` { .text .output title="output" }
✓ template go-service created
✓ template go-service is the default for service
```
