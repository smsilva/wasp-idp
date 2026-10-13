# What stays

Some of what the walkthrough created has no remove command yet, or is refused while something uses it:

| What | Why it stays | To remove it |
|---|---|---|
| The component `hello-api` and the repo `wasp-foundry/hello-api` | there is no `component delete` | delete the repo on GitHub; the component leaves with the cluster |
| The registry `ghcr-wasp-foundry` | `registry remove` is refused (`409`) while a version of the index is in it | the packages stay in GHCR, under the org |
| The catalog and `team-alpha` | the team owns the imported entities ([A team in use](../catalog/team-in-use.md)) | `catalog <kind> delete`, in reverse order ([Clean up, in reverse order](../catalog/cleanup.md)) |
| The GitHub App `wasp-foundry-platform` | lives on GitHub, not in the cluster | the org settings, as the [remove output](scm-connection.md) says |

!!! tip
    `platform-local` stays up for the next round; to tear everything down, go back to [From scratch](../bootstrap/from-scratch.md).
