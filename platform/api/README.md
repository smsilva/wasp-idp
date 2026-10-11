# Platform API

Fachada sobre os CRDs do grupo `platform.wasp.silvios.me` (ADR 0022). Python + FastAPI, roda no cluster de control plane (`platform-local` no target local) com uma ServiceAccount que só enxerga `environments` e as entidades do catálogo (`domains`, `systems`, `resources`, `templates`) no namespace `platform-system`.

## Endpoints

| Método | Caminho | Resposta |
|---|---|---|
| `GET` | `/healthz` | `200`, sem token |
| `GET` | `/v1/me` | `200`, `{"sub", "email", "groups"}` do token |
| `GET` | `/v1/capabilities` | `200`, `{"items": [{"name", "status"}]}`; sem provider, `NoProviderForCapability` |
| `POST` | `/v1/environments` | `202`, body `{"name", "profile": "ephemeral"\|"shared", "expires": "3d"}` |
| `GET` | `/v1/environments` | `200`, `{"items": [...]}` |
| `GET` | `/v1/environments/{name}` | `200` |
| `DELETE` | `/v1/environments/{name}` | `202`; `403` para quem não é o dono nem `platform-admins` |
| `POST` | `/v1/catalog/{kind}` | `201`; `kind` é `domains`, `systems` ou `resources`; body `{"name", "owner", "description", "parent"\|"domain"\|"system", "type"}` |
| `GET` | `/v1/catalog/{kind}` | `200`, `{"items": [...]}` |
| `GET` | `/v1/catalog/{kind}/{name}` | `200`, com `dependents` |
| `DELETE` | `/v1/catalog/{kind}/{name}` | `204`; `409` enquanto houver dependentes |
| `POST` | `/v1/catalog/import` | `200`, plano do import (#190); body `{"documents", "dryRun", "planHash", "source": {"repo", "ref"}}` |
| `POST` | `/v1/catalog/templates` | `201`; só `platform-admins`; body `{"name", "type", "owner", "source": {"repo", "path", "ref"}, "default", "parameters", "copyWithoutRendering", "description"}` |
| `GET` | `/v1/catalog/templates` | `200`, `{"items": [...]}` |
| `GET` | `/v1/catalog/templates/{name}` | `200` |
| `POST` | `/v1/catalog/templates/{name}/default` | `200`; só `platform-admins`; desmarca o padrão anterior do tipo |
| `DELETE` | `/v1/catalog/templates/{name}` | `204`; só `platform-admins`; `409` para o padrão de um tipo com outros templates |
| `POST` | `/v1/catalog/templates:import` | `200`, o mesmo plano do `/v1/catalog/import`, só com templates |
| `POST` | `/v1/cloud/accounts` | `202`, body `{"name", "vendor": "aws", "roleArn", "regions"}`; resposta com `trustPolicy`; `409` sem credencial base ou com `roleArn` já registrado |
| `GET` | `/v1/cloud/accounts` | `200`, `{"items": [...]}`; as próprias, ou todas para `platform-admins` |
| `GET` | `/v1/cloud/accounts/{name}` | `200`, com `trustPolicy`; `403` para quem não é o dono nem `platform-admins` |
| `POST` | `/v1/cloud/accounts/{name}/verify` | `202`; grava `verify-requested-at`, e `verifyPending` fica `true` até o provider responder |
| `DELETE` | `/v1/cloud/accounts/{name}` | `202`; só o dono ou `platform-admins` |
| `GET` | `/v1/catalog/entities` | `200`, todos os kinds com `parent` normalizado; filtros `?kind=domain\|system\|resource` e `?owner=` |

`GET /v1/environments/{name}` traz também `kubeconfigData`, mas só para quem pode usar o ambiente: quem o criou (anotação `platform.wasp.silvios.me/owner`, gravada pela API com o `sub` do token no create), quem está em `platform-admins` e os membros dos times de `spec.sharedWith`. É um kubeconfig pessoal sem credencial (ADR 0028): o usuário dele roda `platform environment credential <nome>`, que chama `POST /v1/environments/{name}/credentials`. A rota confere `can_use`, garante a ServiceAccount da pessoa (o `sub`) no namespace `platform-identities` do vcluster e devolve um token de 10 minutos. A API fala com o vcluster em `https://vcluster.env-<nome>:<porta>` (`PLATFORM_VCLUSTER_SERVER`), com o kubeconfig de administrador que o provider publica no status. Esse kubeconfig de administrador sai só em `GET /v1/environments/{name}/admin-kubeconfig`, e só para `platform-admins`. A lista nunca traz kubeconfig.

`DELETE /v1/environments/{name}` segue a mesma regra: só o dono ou `platform-admins` apagam; os demais recebem `403` (`forbidden`), e o pedido negado não entra no journal. O delete leva o `uid` do objeto checado como precondição: se o ambiente for apagado e recriado com o mesmo nome entre a checagem e o delete, a kube API recusa e a API devolve `409`, em vez de apagar o ambiente novo. Ambientes sem a anotação `owner` (criados antes do PR #184) só são apagáveis por `platform-admins`. A expiração não passa por aqui: o provider apaga pelo `spec.expiresAt` direto na kube API.

Os objetos devolvidos são a visão da API (`name`, `profile`, `status`, `expiresAt`, `kubeconfig`), não o CR cru: clientes não acoplam ao formato dos CRDs.

## Catálogo

Domain, System e Resource são CRDs do grupo `catalog.platform.wasp.silvios.me` (ADR 0023). Component e API não passam por aqui: ficam no `catalog-info.yaml` do repo.

| Kind | Pai | Obrigatórios |
|---|---|---|
| `Domain` | `parent` (outro Domain; opcional, faz um subdomínio) | `owner` |
| `System` | `domain` | `owner`, `domain` |
| `Resource` | `system` | `owner`, `type` (papel: `database`, `topic`…), `system` |

- O pai precisa existir no create; senão `422` (`system 'greeter': domain 'nope' not found`). Campo de outro kind ou faltando também é `422`.
- Apagar com dependentes é `409` com a lista (`system 'greeter' has dependents: resource/greeting-db`).
- Domain: create e delete só para `platform-admins`. System e Resource: qualquer usuário autenticado cria; só quem criou (anotação `platform.wasp.silvios.me/created-by`) ou `platform-admins` apaga. O `owner` é o time e é texto livre até a #186; quem criou é a pessoa.
- Create e delete aceitos entram no journal; os negados, não. O delete leva o `uid` como precondição, como no Environment.

### Templates

`Template` é um CRD do mesmo grupo (ADR 0024): `type` (`service`, `website`, `library`), `default`, `source.{repo,path,ref}`, `parameters` (JSON Schema dos extras, sem `name`, `owner`, `system` e `description`, que vêm da plataforma) e `copyWithoutRendering`. O conteúdo fica no Git; a API não o lê.

- Um padrão por tipo: criar com `default` ou chamar `/default` desmarca o anterior na mesma operação, e cada mudança entra no journal.
- O import converte o `kind: Template` do Backstage: as páginas de `spec.parameters` viram um JSON Schema sem os campos da plataforma nem as dicas `ui:*`; o `url` do `fetch:template` vira `source.path`, relativo ao arquivo (o `path` de cada documento no body); `copyWithoutTemplating` vira `copyWithoutRendering`. Os outros `steps` viram itens `skip` de kind `Step`, com o motivo. Arquivos dentro das pastas de um template (`fetch:template.url`) viram `skip` (`part of template <nome>`): o `catalog-info.yaml` do conteúdo não é um Component.
- Reimportar mantém o `default`; o diff do plano é por campo (`source.ref: v1 → v2`).

## Cloud accounts

`CloudAccount` é um CRD de `platform.wasp.silvios.me` (ADR 0029, `platform/crds/cloudaccount.yaml`): `spec.vendor` (`aws`) e `spec.aws.{roleArn,externalId,regions}`. A API gera o `externalId` (`secrets.token_urlsafe(24)`), nunca o aceita do cliente e o deixa fora do journal. A trust policy devolvida tem como principal o ARN da credencial base, que o provider `aws_account` publica no ConfigMap `aws-base-identity`. Sem esse ConfigMap, a capacidade `cloud-account` fica `NoProviderForCapability` e o registro responde `409`. A validação é do provider (`platform/providers/aws_account/`), que escreve as conditions.

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
