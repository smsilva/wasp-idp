# Sign-in

Every command but `init` talks to the Platform API, which requires a Keycloak token.

| Command | What it does |
|---|---|
| `platform login` | opens the browser on the Google screen (Authorization Code with PKCE, code received on a temporary listener at `127.0.0.1`) |
| `platform login --refresh` | renews the token without the browser, so a team joined since the last login shows at once; signs in again when the session expired |
| `platform login --use-device-code` | prints a URL and a code to confirm on any device: for SSH, containers, or a browser signed in to another Google account |
| `platform whoami` | e-mail and groups, as the API sees them (not read from the local token) |
| `platform logout` | revokes the session in Keycloak and deletes the credentials |

```bash
platform login --use-device-code
```

``` { .text .output title="output" }
Open http://localhost:8180/realms/platform/device?user_code=ABCD-EFGH
and confirm the code ABCD-EFGH
✓ Logged in as you@example.com (platform-admins, platform-users)
```

## Tokens

- Stored in `~/.config/platform/credentials` (permission `0600`), with the client that issued them: refresh and revoke go to that same client.
- The CLI refreshes the access token by itself when less than 60 s remain.
- Team membership changes reach the token on the next refresh: `platform login --refresh` forces one, since Keycloak reads the groups again on every refresh. `platform team member add` of yourself already does it.

## Language

The sign-in pages (Keycloak's, Google's and the CLI's own) are in the language of `locale` in `~/.config/platform/config.yaml`: `en`, written by `platform init`, or `pt-BR`. Without the key, they follow the browser's language. `platform login` asks Keycloak for it (`ui_locales`, which Keycloak forwards to Google) and the CLI's pages use it too. With `--use-device-code` the language selector at the top right of the page still applies.

## Test users

On the local target, `platform login --test-user` (`platform-users`) and `--test-admin` (`platform-admins`) sign in without a browser, for [`scripts/test/cli-smoke` and `scripts/test/cli-e2e`](cli-smoke.md). They are hidden from `--help` and refuse any other target; the reasons are in `platform/keycloak/README.md`.

!!! warning
    The browser must reach Keycloak at `localhost:8180`, the address Google accepts as a redirect. Over SSH, use `--use-device-code` with a tunnel (`ssh -L 8180:localhost:8180`).
