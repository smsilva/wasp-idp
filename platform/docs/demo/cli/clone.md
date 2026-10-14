# Clone the app

By the app name:

```bash
platform catalog component clone hello-api \
  --directory /tmp/hello-api
```

Through the SSH alias of the key that is a member of `wasp-foundry`:

```bash
git -C /tmp/hello-api remote set-url \
  origin \
  git@github.com-personal:wasp-foundry/hello-api.git
```
