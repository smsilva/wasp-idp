# Build the branch

A branch becomes a version without waiting for the merge:

```bash
platform build create \
  --component seat-selection \
  --branch feat/seat-pick \
  --wait
```

``` { .text .output title="output" }
building from feat/seat-pick @ b5f9569 …
✓ app-spec.yaml valid · db (postgres), dns, route
✓ image seat-selection:0.1.0-seat-pick.b5f9569 pushed to ghcr-wasp-foundry (ghcr.io/wasp-foundry/seat-selection)
```

- **Who builds:** GitHub Actions, in the app's own repo. The platform dispatches the workflow, follows the run, checks the `app-spec.yaml` at the built commit and registers the version.
- **The CI holds no platform credential.**
- **Version:** `0.1.0` from the `feat:` commit, plus `-<branch>.<sha7>` outside `main`.
- **Time:** about a minute. Talk through the next page while it runs.
