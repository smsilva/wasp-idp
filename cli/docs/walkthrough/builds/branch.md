# Push a branch

A build starts from a branch on GitHub. `hello-api` came from the `python-service` template when [creating the component](../components/create.md), and the template brings the build workflow.

Clone the component, then push a branch with a `feat:` commit:

```bash
platform catalog component clone hello-api \
  --directory /tmp/hello-api

git -C /tmp/hello-api switch --create feat/greetings

echo "Greets by name." >> /tmp/hello-api/README.md

git -C /tmp/hello-api commit --all --message "feat: greet by name"

git -C /tmp/hello-api push --set-upstream origin feat/greetings
```

The `feat:` prefix matters: the CI decides the version from the [Conventional Commits](https://www.conventionalcommits.org/) since the last `v<version>` tag.
