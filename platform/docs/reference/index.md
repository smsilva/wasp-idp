# Reference

Look up what the Platform API does, a CLI command or an MCP tool. To learn by doing, start with the [walkthrough](../walkthrough/index.md), which uses the CLI.

## API

What the Platform API does for every client, whichever one sends the request.

| Page | About |
|---|---|
| [Status](status.md) | each capability, its providers and whether it works (`platform status`, the `status` tool) |
| [Under the hood](under-the-hood.md) | CRDs, journal, ports |
| [The Forager](forager.md) | how a deploy gets its database, with diagrams |

## CLI

| Page | Commands |
|---|---|
| [Install the CLI](install.md) | prerequisites, `make cli` |
| [Control plane](init.md) | `platform init` |
| [Sign-in](login.md) | `platform login`, `whoami`, `logout` |
| [Environments](environments.md) | `platform environment …` |
| [Catalog](catalog.md) | `platform catalog domain\|system\|resource …`, `platform catalog import` |
| [Templates](templates.md) | `platform catalog template …` |
| [Teams](teams.md) | `platform team …`, environment sharing |
| [Cloud accounts](cloud-accounts.md) | `platform cloud account …` |
| [SCM connections](scm-connections.md) | `platform scm connection …` |
| [Builds](builds.md) | `platform build …`, the build contract with the CI |
| [Registries](registries.md) | `platform registry …` |
| [Workloads](workloads.md) | `platform workload …` |
| [Output formats](output.md) | `--output` / `-o`: `json`, `jsonc`, `yaml`, `yamlc` |
| [Smoke test](cli-smoke.md) | `scripts/test/cli-smoke` and `scripts/test/cli-e2e`: the automated tests of the CLI |
| [Tear down](teardown.md) | removing everything |

`platform <command> --help` explains each argument (which name it takes and where to list it) and ends with `Examples:`, one or two real calls. Every command accepts `--output json`; without a login, every command but `init` answers `not logged in: run 'platform login'`.

## MCP

| Page | About |
|---|---|
| [MCP server](mcp.md) | `platform-mcp`: the Platform API as tools for AI agents, its toolsets and flags |
