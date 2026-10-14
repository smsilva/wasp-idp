# Build the branch

A branch becomes a version without waiting for the merge:

```bash
platform build create \
  --component hello-api \
  --branch feat/greetings \
  --wait
```

``` { .text .output title="output" }
building from feat/greetings @ b5f9569 …
✓ app-spec.yaml valid · db (postgres), dns, route
✓ image hello-api:0.1.0-greetings.b5f9569 pushed to ghcr-wasp-foundry (ghcr.io/wasp-foundry/hello-api)
```

- **Who builds:** GitHub Actions, in the app's own repo. The platform dispatches the workflow, follows the run, checks the `app-spec.yaml` at the built commit and registers the version.
- **The CI holds no platform credential.**
- **Version:** `0.1.0` from the `feat:` commit, plus `-<branch>.<sha7>` outside `main`.
- **Time:** about a minute. Talk through the next page while it runs.
