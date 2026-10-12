# Build a branch

A branch becomes a version without waiting for the merge. The platform does not build: it dispatches the repo's `.github/workflows/platform-build.yaml` on GitHub Actions, follows the run, checks `app-spec.yaml` at the built commit and registers the version. The CI decides the version from the Conventional Commits since the last `v<version>` tag (Commitizen), and holds no platform credential.

`hello-api` came from the `python-service` template when [creating the component](../components/create.md), which brings the workflow. Push a branch with a `feat:` commit, then build it:

```bash
platform catalog component clone hello-api \
  --directory /tmp/hello-api

git -C /tmp/hello-api switch --create feat/greetings

echo "Greets by name." >> /tmp/hello-api/README.md

git -C /tmp/hello-api commit --all --message "feat: greet by name"

git -C /tmp/hello-api push --set-upstream origin feat/greetings

platform build create \
  --component hello-api \
  --branch feat/greetings \
  --wait
```

``` { .text .output title="output" }
building from feat/greetings @ 86a7c08 …
✓ app-spec.yaml valid · db (postgres), dns, route
✓ image hello-api:0.1.0-greetings.86a7c08 pushed to the registry
```

- The version is `0.1.0` (no tag yet: Commitizen starts there), plus `-<branch>.<sha7>` outside `main`. With a `v0.2.0` tag and a `feat:` commit since, it would be `0.3.0-greetings.86a7c08`.
- The image is `ghcr.io/wasp-foundry/hello-api:<version>`, with an OCI manifest carrying the `source`, `revision`, `version` and `me.silvios.wasp.request-id` annotations.
- Only members of the component's owner team (`team-alpha`, [joined earlier](../teams/join.md)) and `platform-admins` build it; anyone signed in reads `build list` and `build get`.
- `--version 1.0.0-rc.1` makes the CI use that version as is.
- A build takes about a minute (the run's `test` job, then the image). Without `--wait`, the command returns at once and `platform build get <build>` shows the steps.
