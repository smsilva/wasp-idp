# Clone and branch

The catalog knows where the repo is, so the clone needs only the app name. The `git remote set-url` line points the push at the SSH alias of the key that is a member of `wasp-foundry`: the default key of this machine belongs to another GitHub account.

```bash
platform catalog component clone hello-api \
  --directory /tmp/hello-api

git -C /tmp/hello-api remote set-url origin git@github.com-personal:wasp-foundry/hello-api.git

git -C /tmp/hello-api switch --create feat/greetings

echo "Greets by name." >> /tmp/hello-api/README.md

git -C /tmp/hello-api commit --all --message "feat: greet by name"

git -C /tmp/hello-api push --set-upstream origin feat/greetings
```

- **Credentials:** git uses your own. The platform hands out none.
- **`feat:`:** the CI computes the version from the Conventional Commits, so this commit makes it `0.1.0`.
- **Without the alias:** the push fails with `Permission to wasp-foundry/hello-api.git denied to <other-user>`. `platform catalog component clone hello-api --https` is the other way out.
