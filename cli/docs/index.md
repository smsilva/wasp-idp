---
hide:
  - navigation
---

# platform CLI

Brings up a **local control plane** and creates **Environments**, each one a virtual Kubernetes cluster (**vcluster**) inside it.

## Where to start

<div class="grid cards" markdown>

-   :material-play-circle-outline: **[Walkthrough](walkthrough/index.md)**

    ---

    Learn by doing: from an empty machine to an environment running, a catalog, teams, a cloud account and a GitHub connection, one step per page, with the real output of each command.

-   :material-presentation-play: **[Demo](demo/index.md)**

    ---

    Show the platform to an audience: an AI agent asking it in plain language over MCP, then the developer journey with the CLI, from a new app to two environments.

-   :material-book-open-variant: **[Reference](reference/index.md)**

    ---

    Look up a command: flags, status values, permissions, ports and what happens under the hood.

-   :material-sitemap-outline: **[Architecture](architecture.md)**

    ---

    How the pieces fit: the CLI talks only to the Platform API, which writes each request as a CRD, and the providers do the work inside `platform-local`.

</div>
