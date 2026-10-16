# Clone the app

By the app name:

```bash
platform catalog component clone seat-selection \
  --directory /tmp/seat-selection
```

Through the SSH alias of the key that is a member of `wasp-foundry`:

```bash
git -C /tmp/seat-selection remote set-url \
  origin \
  git@github.com-personal:wasp-foundry/seat-selection.git
```
