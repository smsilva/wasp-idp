# Templates

A template is the golden path for a type of component (`service`, `website`, `library`; ADR 0024). The content lives in Git; the platform stores the repo, path and ref. `platform init` registers `platform/templates/*` at the last commit of the checkout that exists on GitHub, and the first of each type becomes the default.

| Command | What it does | Who |
|---|---|---|
| `platform catalog template list` | NAME, TYPE, REF, DEFAULT, SOURCE | any user |
| `platform catalog template get <name>` | the registry entry and its parameters | any user |
| `platform catalog template render [<name>\|--from <folder>] --name <component> --output <folder> [--param k=v]...` | renders locally | any user |
| `platform catalog template create <name> --type <type> --owner <team> --repo <url> --path <folder> --ref <ref> [--default]` | registers a template | `platform-admins` |
| `platform catalog template import <path> --repo <url> --ref <ref> [--dry-run] [--yes]` | imports Backstage `kind: Template` or platform `template.yaml` files | `platform-admins` |
| `platform catalog template default <name>` | makes it the default of its type, unmarking the previous one | `platform-admins` |
| `platform catalog template delete <name>` | deletes it; the default of a type with others is `409` until another one is the default | `platform-admins` |

`get` takes `--hide-empty`; its `next:` footer is `render` and `component create --template` with the template ([After a `get`](output.md#after-a-get)).

## Render

`render` fetches the content at the registered ref with git on your machine (or reads `--from`), renders with the Backstage delimiters (`${{ values.x }}`, `dump` filter), copies the `copyWithoutRendering` files as they are and records the origin in `catalog-info.yaml`:

```yaml
platform.wasp.silvios.me/template: <name>@<ref>
```

The default values are `name`, `owner`, `system` and `description`; the template declares the extras, passed with `--param`. Template content is untrusted: rendering is sandboxed, symlinks are refused and only `https` repos are fetched.

## Import

- The scaffolder `steps` appear in the plan as `skip`, with the reason; the platform creates the repo and the discovery finds `catalog-info.yaml`.
- Re-importing keeps whichever template is the default.
- The `--owner` must be an existing team. The Backstage template in `idp/templates/python-service` has `owner: group:default/guests`: import it with `platform catalog import` together with the `guests` `Group`, or create the team first.
