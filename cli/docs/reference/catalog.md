# Catalog

Domains, systems and shared resources that the platform stores (ADR 0023). The `--owner` is always a team that already exists ([Teams](teams.md)). Components and APIs are not in the platform catalog yet.

| Command | What it does |
|---|---|
| `platform catalog domain create <name> --owner <team> [--parent <domain>]` | creates a domain or, with `--parent`, a subdomain |
| `platform catalog system create <name> --domain <domain> --owner <team>` | creates a system |
| `platform catalog resource create <name> --type <role> --system <system> --owner <team>` | creates a shared resource; `--type` is the role (`database`, `topic`, `queue`, `bucket`), never the cloud service |
| `platform catalog list [--kind domain\|system\|resource] [--owner <team>]` | KIND, NAME, PARENT, OWNER |
| `platform catalog <kind> list\|get\|delete <name>` | per kind; `get` shows the dependents |

| Action | Who |
|---|---|
| create or delete a domain | `platform-admins` |
| create a system or a resource | any user |
| delete a system or a resource | whoever created it, or `platform-admins` |

An entity with dependents is not deleted: the API answers `409` naming them, so deleting goes in the reverse order.

## Import from Backstage

```bash
platform catalog import <path>... \
  [--repo <url> --ref <ref>] \
  [--dry-run] \
  [--yes]
```

Imports Backstage files (a file or a folder, recursive `*.yaml`/`*.yml`). The Platform API computes the plan and nothing is written before the confirmation; `--dry-run` shows only the plan, `--yes` applies without asking.

| Action | Meaning |
|---|---|
| `create` | does not exist on the platform |
| `update` | exists and changes; the detail shows `field: before → after` |
| `unchanged` | exists and is identical |
| `skip` | not imported: Component and API arrive through discovery (#205), User stays in Keycloak, files inside a template's content, the `steps` of a Backstage template |
| `forbidden` | no permission |
| `error` | missing field or broken reference; the detail names the field and the file |

- A `Group` becomes a team (`platform-admins` only; members are not imported) and enters the plan before the other entities.
- With any `forbidden` or `error`, nothing is applied.
- The import never deletes. A field missing from the file is removed from the entity.
- If the catalog changes between the plan and the confirmation, the API refuses and the CLI shows the new plan.
- Templates (`kind: Template`) need `--repo` and `--ref`; without them they become `error` and the rest of the plan goes on.
