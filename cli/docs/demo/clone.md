# Clone and branch

Clone by the app name:

```bash
platform catalog component clone hello-api \
  --directory /tmp/hello-api
```

Push through the SSH alias of the key that is a member of `wasp-foundry`:

```bash
git -C /tmp/hello-api remote set-url origin git@github.com-personal:wasp-foundry/hello-api.git
```

A new branch:

```bash
git -C /tmp/hello-api switch --create feat/greetings
```

A change and a `feat:` commit, which makes the version `0.1.0`:

```bash
echo "Greets by name." >> /tmp/hello-api/README.md
```

```bash
git -C /tmp/hello-api commit --all --message "feat: greet by name"
```

Push the branch:

```bash
git -C /tmp/hello-api push --set-upstream origin feat/greetings
```
