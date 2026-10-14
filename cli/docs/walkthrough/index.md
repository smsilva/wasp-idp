# Walkthrough

A walkthrough to demonstrate the `platform` CLI **starting from scratch**: no cluster, no config and no CLI installed. Follow it in order, one step per page: each step builds on the previous ones. To look up a command, a flag or a status, use the [reference](../reference/index.md).

## Ideas to make the walkthrough repeatable

??? abstract "Open issues for the walkthrough"

    - **Script `scripts/demo/cli-walkthrough` (#178):** runs the steps in sequence, pauses before each one (Enter to continue) and stops at sign in waiting for the device code. Use it to present and to check before a merge.
    - **Measure (#180):** record the time of each step to notice when `init` or the provider get slower.
    - **Record (#181):** `asciinema rec` during the walkthrough produces a lightweight terminal video for the README and the deck.
    - **Evolve with the CLI (#182):** each new command (`release create`, `catalog component create`) is added here as a step, with the expected output.
