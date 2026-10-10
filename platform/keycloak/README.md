# Keycloak

Broker de identidade da plataforma (ADR 0021): o Google autentica, o Keycloak guarda os grupos e emite os tokens que a Platform API valida.

## O que o `platform init --target local` faz

- Sobe o Keycloak (`deploy/keycloak.yaml`) no namespace `platform-auth` do `platform-local`, em `start-dev`, com o banco H2 embutido num PVC. Ele fica exposto em `http://localhost:8180`, pela porta 8180 do load balancer do k3d.
- Gera a senha do admin do Keycloak uma vez e a guarda no Secret `keycloak-admin`.
- Grava `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` e o `--admin` no Secret `keycloak-google`. Um `init` posterior sem essas variáveis reaproveita o que está lá.
- Aplica o realm `realm-platform.yaml` com o keycloak-config-cli (`deploy/realm-import.yaml`). O import é idempotente, e o `init` recria o Job a cada execução.
- Grava `issuer` e `client_id` em `~/.config/platform/config.yaml`.

## Issuer

`KC_HOSTNAME=http://localhost:8180` fixa o issuer de todo token em `http://localhost:8180/realms/platform`. Dentro do cluster, a Platform API busca o JWKS pela URL interna (`http://keycloak.platform-auth.svc:8080`) e compara o `iss` com a URL pública. Sem o hostname fixo, os dois valores divergem e a validação falha.

## Realm `platform`

| Item | Valor |
|---|---|
| Grupos | `platform-admins`, `platform-users` (default de todo usuário novo) |
| Client `platform-cli` | público, Authorization Code + PKCE (S256), device code, redirect `http://127.0.0.1/*` |
| Client `platform-api` | bearer-only; o scope `platform-api-audience` põe `platform-api` no `aud` |
| Claim `groups` | nomes sem path, do scope `platform-groups` |
| Identity Provider | `google`; o mapper `bootstrap-admin` põe o e-mail do `--admin` em `platform-admins` |

Sem `GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET`, o realm sobe sem o Identity Provider e o `init` avisa. Sem `--admin`, o mapper `bootstrap-admin` fica de fora.

## Lado do Google (uma vez, manual)

1. No Google Cloud, configure a tela de consentimento OAuth como External, em modo **Testing**, com os e-mails que vão logar em **Test users**. Assim não há processo de verificação.
2. Crie um OAuth client do tipo **Web application** com o redirect URI `http://localhost:8180/realms/platform/broker/google/endpoint`. O Google aceita `localhost`, mas rejeita IP e domínio local inventado; por isso o Keycloak fica em `localhost`. Um mesmo client pode servir ao Backstage e ao Keycloak, com um redirect URI para cada.
3. Exporte as credenciais antes do `init`:

   ```bash
   export GOOGLE_CLIENT_ID=<id>.apps.googleusercontent.com
   export GOOGLE_CLIENT_SECRET=<secret>
   platform init --target local --admin <seu-email>
   ```

   Os valores reais ficam fora do repo.

## Verificar

Abra `http://localhost:8180/realms/platform/account`, clique em **Google** e entre com o e-mail do `--admin`. O usuário deve aparecer em `platform-admins` e `platform-users`.

| Sintoma | Causa |
|---|---|
| `Error 400: redirect_uri_mismatch` no Google | falta o redirect URI acima no OAuth client |
| "Unexpected error when authenticating with identity provider" e `invalid_client` no log do Keycloak | client secret inválido ou revogado: gere outro e rode o `init` de novo |

A senha do admin do console (`http://localhost:8180/admin`, usuário `admin`):

```bash
kubectl --context k3d-platform-local --namespace platform-auth get secret keycloak-admin \
  --output jsonpath='{.data.password}' | base64 --decode
```
