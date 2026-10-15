# Wrap up

Delete the environments, then the repo and its images, so the next run starts clean:

```bash
platform environment delete demo

platform environment delete greetings-test

gh repo delete wasp-foundry/hello-api --yes

gh api \
  --method DELETE \
  orgs/wasp-foundry/packages/container/hello-api

rm -rf /tmp/hello-api
```

The component stays in the catalog index. `gh` needs the `delete_repo` and `delete:packages` scopes: `gh auth refresh --scopes delete_repo,delete:packages`.
