# A branch and a change

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
