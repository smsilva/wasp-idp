# Build a branch

A branch becomes a version **without waiting for the merge**:

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

The platform does not build. It:

1. dispatches the repo's `.github/workflows/platform-build.yaml` on GitHub Actions, with the image to push;
2. follows the run;
3. checks `app-spec.yaml` at the built commit;
4. registers the version.

The CI holds no platform credential. A build takes about a minute: the run's `test` job, then the image.

- **Without `--wait`**, the command returns at once and `platform build get <build>` shows the steps.
- **Who builds:** members of the component's owner team (`team-alpha`, [joined earlier](../teams/create.md)) and `platform-admins`. Anyone signed in reads `build list` and `build get`.
