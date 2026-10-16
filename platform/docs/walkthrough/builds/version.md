# The version and the image

The build of the previous page produced `seat-selection:0.1.0-seat-pick.b5f9569`.

## Version

The CI computes it with Commitizen, from the Conventional Commits since the last `v<version>` tag:

- **`0.1.0`**: no tag yet, so Commitizen starts there. With a `v0.2.0` tag and a `feat:` commit since, it would be `0.3.0`.
- **`-seat-pick.b5f9569`**: `-<branch>.<sha7>`, added outside `main`.

`--version 1.0.0-rc.1` makes the CI use that version as is.

## Image

The image is `ghcr.io/wasp-foundry/seat-selection:<version>`, in the default registry `ghcr-wasp-foundry` ([GHCR of the GitHub org](../registry/ghcr/register.md)). Its OCI manifest carries the `source`, `revision`, `version` and `me.silvios.wasp.request-id` annotations.

`--registry <name>` picks another registry. For GHCR it must be the one of the repo's org, or the build is refused with `RegistryNotWritableByCI`.
