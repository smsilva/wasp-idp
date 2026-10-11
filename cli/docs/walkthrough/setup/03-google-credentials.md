# Google credentials

O **OAuth client do Google** é configurado uma vez (veja `platform/keycloak/README.md`). Guarde o id e o secret num cofre de segredos e carregue-os no shell antes do `init`; na tela, **mostre só o prefixo**:

```bash
export GOOGLE_CLIENT_ID=<id>.apps.googleusercontent.com

export GOOGLE_CLIENT_SECRET=<secret>

echo "${GOOGLE_CLIENT_ID:0:12}… ${GOOGLE_CLIENT_SECRET:0:3}…"
```
