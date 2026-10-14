# Renew the token

Someone else added to a team, by another admin, renews their own token. No browser: Keycloak reads the groups again on a refresh.

```bash
platform login --refresh

platform whoami
```

``` { .text .output title="output" }
✓ Logged in as you@example.com (platform-admins, platform-users, team-alpha)
you@example.com (platform-admins, platform-users, team-alpha)
```

When the session has expired, `--refresh` signs in again through the browser.
