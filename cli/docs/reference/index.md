# Reference

Look up a command, a flag or a status. To learn the CLI by doing, start with the [walkthrough](../walkthrough/index.md).

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
| [JSON output](json-output.md) | `--output json` |
| [Under the hood](under-the-hood.md) | CRDs, journal, ports |
| [Tear down](teardown.md) | removing everything |

Every command accepts `--output json`; without a login, every command but `init` answers `not logged in: run 'platform login'`.
