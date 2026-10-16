# Push a branch

A build starts from a branch on GitHub. `seat-selection` came from the `python-service` template when [creating the component](../components/create.md), and the template brings the build workflow.

Clone the component, then push a branch with a `feat:` commit:

```bash
platform catalog component clone seat-selection \
  --directory /tmp/seat-selection

git -C /tmp/seat-selection switch --create feat/seat-pick

echo "Picks a seat at check-in." >> /tmp/seat-selection/README.md

git -C /tmp/seat-selection commit --all --message "feat: pick a seat at check-in"

git -C /tmp/seat-selection push --set-upstream origin feat/seat-pick
```

The `feat:` prefix matters: the CI decides the version from the [Conventional Commits](https://www.conventionalcommits.org/) since the last `v<version>` tag.
