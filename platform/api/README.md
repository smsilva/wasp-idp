# Platform API

Fachada sobre os CRDs do grupo `platform.wasp.silvios.me` (ADR 0022). Python + FastAPI, roda no cluster de control plane (`platform-local` no target local) com uma ServiceAccount que só enxerga `environments` no namespace `platform-system`.

## Endpoints

| Método | Caminho | Resposta |
|---|---|---|
| `GET` | `/healthz` | `200`, sem token |
| `GET` | `/v1/me` | `200`, `{"sub", "email", "groups"}` do token |
| `GET` | `/v1/capabilities` | `200`, `{"items": [{"name", "status"}]}`; sem provider, `NoProviderForCapability` |
| `POST` | `/v1/environments` | `202`, body `{"name", "profile": "ephemeral"\|"shared", "expires": "3d"}` |
| `GET` | `/v1/environments` | `200`, `{"items": [...]}` |
| `GET` | `/v1/environments/{name}` | `200` |
| `DELETE` | `/v1/environments/{name}` | `202` |

`GET /v1/environments/{name}` traz também `kubeconfigData`, o acesso de administrador ao ambiente, mas só para quem o criou (anotação `platform.wasp.silvios.me/owner`, gravada pela API com o `sub` do token no create) ou para quem está em `platform-admins`. A lista nunca o traz.

Os objetos devolvidos são a visão da API (`name`, `profile`, `status`, `expiresAt`, `kubeconfig`), não o CR cru: clientes não acoplam ao formato dos CRDs.

## Escrita

- Toda escrita passa pela interface `StateWriter` (`state.py`); a implementação é `KubeApplyWriter`, que aplica direto na kube API.
- No create, a API grava `Ready=False, reason=NoProviderForCapability`. O provider substitui a condition quando assume; se ele já tiver tocado o objeto, a API não sobrescreve (concorrência otimista por `resourceVersion`).

## Journal

Nesta fatia, o journal é um arquivo append-only JSON Lines em `/var/lib/platform/journal.jsonl`, num PVC (`platform-api-journal`). Cada pedido aceito gera uma linha com `applied: false` **antes** de ser aplicado e outra com o mesmo `id` e `applied: true` depois. O Postgres substitui o arquivo com a #172.

A expiração de um ambiente é aplicada pelo provider direto no CR e não passa pelo journal.

## Autenticação

Toda rota `/v1/*` exige `Authorization: Bearer <token>` emitido pelo Keycloak (ADR 0021). A validação (`auth.py`, `pyjwt`):

- assinatura RS256 pelo JWKS, buscado pela URL interna (`PLATFORM_OIDC_JWKS_URL`, o Service `keycloak.platform-auth`);
- `iss` igual ao issuer público (`PLATFORM_OIDC_ISSUER`, `http://localhost:8180/realms/platform`), o mesmo `KC_HOSTNAME` do Keycloak;
- `aud` contém `platform-api`; `exp` e `sub` obrigatórios.

Sem token ou com token inválido, `401` com `WWW-Authenticate: Bearer`; o motivo exato não vai na resposta. `require_group("platform-admins")` responde `403` quando o grupo falta na claim `groups`. O autor no journal é `sub (e-mail)`.

A validação mora na API, não só na borda: funciona igual em qualquer target, e a API precisa das claims para o journal e a autorização. Um ingress ou mesh validando antes é camada extra, não substituto.

O `TrustedHostMiddleware` continua: a API recusa (`400`) header `Host` fora de `PLATFORM_ALLOWED_HOSTS` (default `127.0.0.1,localhost`), contra DNS rebinding.

## Erros

Toda resposta de erro tem o formato `{"error": {"code", "message"}}`, com `code` em `bad_request`, `unauthorized`, `forbidden`, `not_found`, `conflict` ou `invalid_request`. Operações longas futuras devolverão um ID de operação em vez de bloquear a requisição.

## Desenvolvimento

```bash
cd platform/api
uv sync
uv run pytest
```

A imagem é buildada e importada no k3d pelo `platform init --target local`.
