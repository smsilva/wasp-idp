# Teams

A team is a Keycloak group that the Platform API maintains (ADR 0026). It owns catalog entities and receives shared environments.

| Command | What it does | Who |
|---|---|---|
| `platform team list` | teams | any user |
| `platform team get <team>` | members (EMAIL, USERNAME) | any user |
| `platform team create <team>` | creates a team | `platform-admins` |
| `platform team delete <team>` | deletes a team; a team in use (owning catalog entities or with shared environments) is `409` | `platform-admins` |
| `platform team member add\|remove <team> <email>` | changes members | `platform-admins` |

- The member must have signed in to the platform once, with a verified e-mail; before that, the API answers `404`.
- The team reaches the token on the next refresh. Adding yourself renews your token at once (`✓ … · token renewed, <team> is in it`); anyone else runs `platform login --refresh`, and `platform whoami` then shows it.

## Sharing environments

```bash
platform environment share <name> \
  --team <team>

platform environment unshare <name> \
  --team <team>
```

`platform environment create … --share-with <team>` shares at creation. An environment starts private. The owner shares it with teams they belong to; only `platform-admins` share with other teams. Team members see the environment in `environment list` and receive the kubeconfig in `environment get`; deleting, sharing and unsharing stay with the owner and the admins.

Each person has their own identity in the vcluster. Unsharing deletes the identities of everyone who is not the owner, and removing someone from a team deletes that person's identity in the environments shared with it: within seconds, their kubectl receives `environment '<name>' is not yours nor shared with your teams`. Whoever still has access through another team gets a new token on the next command.
