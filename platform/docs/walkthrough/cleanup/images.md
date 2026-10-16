# Delete the repo and its images

The repo `wasp-foundry/seat-selection` and the images its CI pushed to `ghcr.io/wasp-foundry/seat-selection` live on GitHub, not in the cluster: no `platform` command removes them. Deleting the repo leaves the package behind, unlinked, so delete both.

```bash
gh repo delete wasp-foundry/seat-selection --yes

gh api \
  --method DELETE \
  orgs/wasp-foundry/packages/container/seat-selection
```

Deleting the package takes every version (tag) of the image at once.

!!! note
    `gh repo delete` needs the `delete_repo` scope and the package delete needs `delete:packages`. Without them GitHub answers `403`; add them with `gh auth refresh --hostname github.com --scopes delete_repo,delete:packages`.

List the container packages left in the org, with the repo each one is linked to (`-` marks one with no repo):

```bash
gh api "orgs/wasp-foundry/packages?package_type=container" \
  --jq '.[] | "\(.name)\t\(.repository.name // "-")"'
```

`seat-selection` is no longer in the list. A package that still shows `-` was left by an earlier round; delete it the same way.

!!! tip
    An org owner can restore a deleted package for 30 days, from the org settings (Packages). The next round of the walkthrough pushes `seat-selection` again from a new repo, and that new package starts with no versions.
