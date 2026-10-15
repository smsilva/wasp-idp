# Wrap up

Delete the environments, then the repo and its images, so the next run starts clean. One script does it all, from the repo root:

```bash
scripts/demo/cleanup
```

It lists what is still there, asks before deleting (`--yes` skips the question) and waits until the environments are gone. What an earlier run already removed is skipped, so it also works as a first step of [Get ready](before.md). By hand, it is:

```bash
platform environment delete demo

platform environment delete greetings-test

gh repo delete wasp-foundry/hello-api --yes

gh api \
  --method DELETE \
  orgs/wasp-foundry/packages/container/hello-api

rm -rf /tmp/hello-api
```

The component stays in the catalog index. `gh` needs the `delete_repo` and `delete:packages` scopes, which the script checks before deleting anything: `gh auth refresh --scopes delete_repo,delete:packages`.
