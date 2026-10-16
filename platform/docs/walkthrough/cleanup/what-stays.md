# What stays

Some of what the walkthrough created has no remove command yet, or is refused while something uses it:

| What | Why it stays | To remove it |
|---|---|---|
| The component `seat-selection` and the repo `wasp-foundry/seat-selection` | there is no `component delete` | [delete the repo and its images](images.md); the component leaves with the cluster |
| The registry `ghcr-wasp-foundry` | `registry remove` is refused (`409`) while a version of the index is in it | it leaves with the cluster; the images in GHCR go with the [repo](images.md) |
| The catalog and `team-alpha` | the team owns the imported entities ([A team in use](../catalog/team-in-use.md)) | `catalog <kind> delete`, in reverse order ([Clean up, in reverse order](../catalog/cleanup.md)) |
| The GitHub App `wasp-foundry-platform` | lives on GitHub, not in the cluster | the org settings, as the [remove output](scm-connection.md) says |

!!! tip
    `platform-local` stays up for the next round; to tear everything down, go back to [From scratch](../bootstrap/from-scratch.md).
