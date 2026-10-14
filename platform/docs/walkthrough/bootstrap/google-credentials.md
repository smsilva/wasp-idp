# Google credentials

The **Google OAuth client** is configured once (see `platform/keycloak/README.md`). Store the id and secret in a secrets vault and load them into the shell before `init`; on screen, **show only the prefix**:

```bash
export GOOGLE_CLIENT_ID=<id>.apps.googleusercontent.com

export GOOGLE_CLIENT_SECRET=<secret>

echo "${GOOGLE_CLIENT_ID:0:12}… ${GOOGLE_CLIENT_SECRET:0:3}…"
```
