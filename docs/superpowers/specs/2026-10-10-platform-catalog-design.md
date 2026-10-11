# Platform Catalog — Design

Issue [#191](https://github.com/smsilva/wasp-idp/issues/191) (fatia 1). Relacionadas: [#190](https://github.com/smsilva/wasp-idp/issues/190) (import no formato Backstage), [#186](https://github.com/smsilva/wasp-idp/issues/186) (grupos e compartilhamento).

## Contexto

O deck (`docs/presentation/idp.yaml`) apresenta o modelo mental do Backstage como o catálogo da plataforma: Domain e System na visão de negócio; Component, API e Resource na visão de engenharia. Também mostra o `app-spec.yaml` no modelo do Score e o orquestrador que traduz a declaração em recursos. Na issue #145 esse orquestrador foi chamado de **Forager**.

Hoje o catálogo vive só no Backstage (`idp/`). Domain, System, Resource e Group ficam em arquivos de `idp/catalog/`, carregados como locations. Component e API ficam no `catalog-info.yaml` de cada repo da org `wasp-foundry`, encontrados pelo discovery do ADR 0020. A Platform API não sabe nada do catálogo: `GET /v1/capabilities` devolve `catalog: NoProviderForCapability`.

O ADR 0022 diz que os clientes (CLI, Backstage, agentes) falam só com a Platform API. Ainda assim, o catálogo não pode depender do Backstage: **se o Backstage cair, a plataforma continua funcionando com o catálogo disponível.**

## Decisões

### 1. Cada entidade tem uma casa só

A pergunta que separa as entidades não é quem as cria (a CLI cria todas), e sim onde o registro fica guardado e, portanto, como ele muda depois.

| Entidade | Casa do registro | Como muda |
|---|---|---|
| `Domain` (com `parent` para subdomínio) | CRD na plataforma | CLI/API |
| `System` | CRD na plataforma | CLI/API |
| `Resource` compartilhado (referenciado por `id` no Score) | CRD na plataforma | CLI/API |
| `Resource` só de uma app (sem `id` no Score) | derivado do Score pelo Forager | PR no `app-spec.yaml` |
| `Component` | `catalog-info.yaml` no repo | PR no repo; a CLI pode abrir o PR |
| `API` | `openapi.yaml` + `catalog-info.yaml` no repo | PR no repo |
| `Group`/`User` | Keycloak (#186) | fora do catálogo |

Domain, System e o Resource compartilhado não pertencem a nenhum repo. Por isso a plataforma os guarda como CRDs (ADR 0022). Component e API mudam junto com o código, no mesmo PR (slide `context-next-to-code`). Por isso eles ficam no repo, e a plataforma os descobre.

### 2. "Catalog" é o espaço de nomes, não uma entidade

Não existe um objeto `Catalog` contendo os outros. Um objeto assim só se justificaria com vários catálogos (multi-tenant), e o Backstage já resolve esse caso com `metadata.namespace`. O agrupamento aparece em três lugares:

- **CRDs:** o grupo `catalog.platform.wasp.silvios.me`, separado de `platform.wasp.silvios.me` (Environment, Release, ResourceRequest).
- **API:** as rotas `/v1/catalog/...`.
- **CLI:** o grupo de comandos `platform catalog <kind> <verbo>`.

### 3. Resource do catálogo ≠ instância num ambiente

São três camadas, e só a primeira é entidade do catálogo:

| Camada | O que é | Quem cria |
|---|---|---|
| Resource do catálogo | identidade lógica descrita pelo papel ("o banco do greeter"), com owner e System, uma só para todos os ambientes | CLI/API (compartilhado) ou Forager a partir do Score (só da app) |
| Recurso no Score | o que um workload precisa (`db: {type: postgres}`) | o dev, no repo |
| `ResourceRequest` | a instância num ambiente, com o modo resolvido (`provision`/`compose`/`bind`) | o Forager, nunca uma pessoa |

O elo entre o Score e o catálogo é o campo `resources.<nome>.id` do próprio Score. Sem `id`, o recurso é só da app, e o Forager deriva um Resource com o nome `<component>-<nome>`. Com `id`, o recurso aponta para um Resource que alguém cadastrou, e dois Components com o mesmo `id` compartilham o recurso. Um `id` que não existe no catálogo é recusado no build, com o motivo (slide `deterministic-gate`).

O que a plataforma oferece ao dev é o **tipo** (`postgres`), não um Resource. A instância compartilhada de Postgres (`shared-pg`) pode aparecer no catálogo como Resource de `team-platform` no System `platform`, mas ela é alvo do modo `compose`, não algo que o dev escolhe.

### 4. O Backstage lê a plataforma; ninguém depende de ninguém

A Platform API guarda as entidades da organização, e o Backstage as consome por um entity provider (fatia 3). Component e API continuam chegando ao Backstage pelo discovery do ADR 0020.

| Cai | Efeito |
|---|---|
| Backstage | Nada: a CLI e a API leem os CRDs. |
| Platform API | O Backstage mantém as entidades da última leitura e registra a falha de atualização no log. |
| GitHub | `catalog list` funciona para Domain, System e Resource. Component depende do discovery (fatia 2). |

### 5. Owner é texto livre até a #186

`spec.owner` é um nome de grupo (`team-alpha`), validado só no formato. Não existe ligação com grupos do Keycloak até a #186. A forma `group:default/team-alpha` do Backstage é convertida para `team-alpha` pelo import (#190) e pelo export para o Backstage (fatia 3).

### 6. A criação de Component é `platform catalog component create`

Um único caminho para criar qualquer entidade do catálogo. `--type` é a classificação do Backstage (`service`, `website`, `library`) e escolhe o golden path padrão. `--template` só existe para fugir do padrão. O ciclo de vida da app fica fora do `catalog` e referencia o Component por `--component` (`platform build create --component greeting-api`). Os comandos ilustrativos do deck (`diagrams/journey/build.py`) passam para esse vocabulário num PR à parte.

## Fatias

| Fatia | Escopo | Issue |
|---|---|---|
| 1 | Domain, System e Resource na Platform API e na CLI | #191 |
| 1b | Import de arquivos no formato Backstage com plano revisado | #190 |
| 2 | `component create` com golden path (repo + `catalog-info.yaml` + `app-spec.yaml`), discovery de Component/API, `component clone` e `component update` por PR | a criar |
| 3 | Entity provider no Backstage lendo a Platform API; `idp/catalog/` deixa de ser location | a criar |
| 4 | Forager: Score → Resource derivado e `ResourceRequest` | #263 |

Este spec detalha só a fatia 1. As outras ficam registradas aqui para manter o modelo, e cada uma terá o seu spec.

## Fatia 1 — Domain, System e Resource

### CRDs

Três CRDs namespaced em `platform-system`, grupo `catalog.platform.wasp.silvios.me`, versão `v1alpha1`, um arquivo cada em `platform/crds/` (`catalog-domain.yaml`, `catalog-system.yaml`, `catalog-resource.yaml`). O `platform init` já aplica a pasta inteira.

| Kind | Plural | `spec` |
|---|---|---|
| `Domain` | `domains` | `owner` (obrigatório), `description`, `parent` (outro Domain: subdomínio) |
| `System` | `systems` | `owner` (obrigatório), `description`, `domain` (obrigatório) |
| `Resource` | `resources` | `owner` (obrigatório), `description`, `type` (obrigatório, papel: `database`, `topic`, `queue`, `bucket`…), `system` (obrigatório) |

- Nome: rótulo DNS-1123 (até 63 caracteres, minúsculas, dígitos, hífen), único por kind.
- `owner`: mesmo formato do nome, sem prefixo `group:`.
- `type` do Resource: mesmo formato, texto livre, como no Backstage.
- Sem `status` nesta fatia: são entidades declarativas, sem reconciliação.
- `additionalPrinterColumns`: Owner e o pai (`Parent`, `Domain` ou `System`), para o `kubectl get` ajudar no diagnóstico.
- Quem criou fica na anotação `platform.wasp.silvios.me/created-by`, com o `sub` do token. Ela não é o `owner`: o owner é um time, e o criador é uma pessoa.

`Domain.parent` é opcional, porque um Domain raiz não tem pai. `System.domain` e `Resource.system` são obrigatórios, como no exemplo `communication`: nenhum System ou Resource fica solto.

### Regras da API

1. **Referências válidas:** `Domain.parent`, `System.domain` e `Resource.system` precisam existir no momento do create. Caso contrário, `422` com o campo e o nome (`system 'greeter': domain 'messaging' not found`).
2. **Ciclo:** impossível nesta fatia, porque não há update e o pai precisa existir antes do filho.
3. **Apagar com dependentes:** `409` listando os dependentes (`domain 'communication' has dependents: domain/messaging, system/greeter`).
   - Domain: subdomínios e Systems.
   - System: Resources (e Components na fatia 2).
   - Resource: nenhum nesta fatia.
4. **Nome duplicado:** `409`, como no Environment.
5. **Autorização:**
   - `Domain` (create e delete): só `platform-admins`. Domain é estrutura da organização.
   - `System` e `Resource`: qualquer usuário autenticado cria. Só quem criou (anotação `created-by`) ou `platform-admins` apaga. É a regra `is_owner_or_admin` do Environment, aplicada à anotação do catálogo.
   - A #186 troca "quem criou" por "membro do grupo owner", quando os grupos de time existirem no Keycloak.
6. **Journal:** create e delete aceitos são gravados como no Environment (`kind` = `Domain`, `System`, `Resource`). O negado não é gravado.
7. **Delete com precondição de `uid`**, como na #185.

**Limitação aceita:** a checagem de dependentes não é atômica. Um filho criado entre a checagem e o delete do pai fica com referência pendurada. Com escrita só pela Platform API e baixo volume, o risco é pequeno. Um finalizer no pai fecharia a brecha e fica registrado como evolução, não nesta fatia.

### Rotas

| Método | Rota | Resposta |
|---|---|---|
| `POST` | `/v1/catalog/{kind}` | `201`, a visão da entidade |
| `GET` | `/v1/catalog/{kind}` | `200`, `{"items": [...]}` |
| `GET` | `/v1/catalog/{kind}/{name}` | `200`, a visão da entidade, com `dependents` |
| `DELETE` | `/v1/catalog/{kind}/{name}` | `204` |
| `GET` | `/v1/catalog/entities` | `200`, `{"items": [...]}` de todos os kinds; filtros `?kind=` e `?owner=` |

`{kind}` aceita `domains`, `systems` e `resources`. Um kind desconhecido devolve `404`. O create é síncrono (`201`, e não o `202` do Environment) porque não há provider: a entidade está pronta quando é gravada. O `GET /v1/capabilities` passa a dizer `catalog: Active`.

Visão da API (clientes não acoplam ao CR):

```json
{"kind": "System", "name": "greeter", "owner": "team-alpha", "description": "…",
 "domain": "messaging", "createdAt": "2026-10-10T00:00:00Z"}
```

O pai aparece no nome do campo do kind (`parent`, `domain`, `system`). Na lista agregada (`/v1/catalog/entities`), cada item traz também `parent` normalizado, para a tabela da CLI.

### CLI

```bash
platform catalog domain create communication --owner team-alpha
platform catalog domain create messaging --parent communication --owner team-alpha
platform catalog system create greeter --domain messaging --owner team-alpha
platform catalog resource create greeting-db --type database --system greeter --owner team-alpha

platform catalog list [--kind domain|system|resource] [--owner team-alpha]
platform catalog domain list
platform catalog system get greeter
platform catalog system delete greeter
```

- `platform catalog list` mostra a tabela `KIND NAME PARENT OWNER`, ordenada por kind (Domain, System, Resource) e nome.
- `get` mostra os campos e os dependentes.
- `--description` é opcional em todo create.
- `--output json` vale em todos os comandos, como no `environment`.
- Mensagens de erro vêm da API (`422`, `409`, `403`), sem tradução na CLI.
- Código em `cli/src/wasp_platform/commands/catalog.py`, com um sub-typer por kind registrado em `catalog`. Métodos novos em `client.py`.

### Código da API

- `platform/api/src/platform_api/catalog.py`: os kinds (plural, campo do pai, kind do pai), `manifest`, `view` e as regras de referência e dependentes. São funções puras, no padrão de `environments.py`.
- As rotas ficam num `APIRouter` criado em `catalog.py` e incluído no `create_app`, para o `app.py` não crescer com cada kind.
- `state.py`: o `KubeApplyWriter` hoje usa um `GROUP` fixo. Ele passa a resolver o grupo pelo plural (`environments` → `platform.wasp.silvios.me`; `domains`, `systems`, `resources` → `catalog.platform.wasp.silvios.me`).
- `is_owner_or_admin` passa a receber a anotação a conferir, ou ganha uma variante para `created-by`. A escolha fica no plano de implementação.
- RBAC do ServiceAccount da API (`platform/api/deploy/platform-api.yaml`): `get`, `list`, `create` e `delete` nos três plurais do grupo novo.

### Testes

- **API:** em `platform/api/tests/`, um arquivo novo `test_catalog.py`. O `FakeState` de `test_api.py` hoje indexa objetos só pelo nome e ignora o plural. Ele passa a indexar por `(plural, name)` e vai para `tests/fakes.py`, compartilhado pelos dois arquivos. Casos:
  - create dos três kinds;
  - `422` por pai inexistente;
  - `409` por duplicado e por dependentes;
  - `403` para não admin criando Domain e para outro usuário apagando System;
  - admin apagando;
  - journal com create e delete e sem o negado;
  - lista agregada com filtros;
  - `capabilities` com `catalog: Active`.
- **CLI:** `cli/tests/test_catalog.py` com `httpx.MockTransport`, no padrão de `test_environment.py`: tabela, JSON e repasse da mensagem de erro.
- **Ponta a ponta no `platform-local`, com o Backstage parado:**
  - a sequência da seção CLI;
  - o `delete` do Domain com dependentes recusado;
  - a limpeza na ordem inversa;
  - `kubectl get domains.catalog.platform.wasp.silvios.me` mostrando as colunas.

### Documentação

- **ADR 0023:** "Catálogo da plataforma: entidades da organização como CRDs, entidades de código no repo, Backstage como leitor". Registra as decisões 1 a 4 e o nome Forager para o resolvedor do ADR 0022.
- **`platform/api/README.md`:** rotas e regras do catálogo.
- **`cli/docs/index.md` e `cli/docs/walkthrough.md`:** uma etapa nova de catálogo, com a regra da #182.

## Fora de escopo da fatia 1

- Update (mudar owner, descrição, pai). O import (#190) vai precisar de update e o traz.
- `lifecycle` (`experimental`/`production`/`deprecated`, slide `ip-lifecycle`).
- Component, API, golden path e discovery (fatia 2).
- O Backstage lendo a plataforma (fatia 3). Até lá, `idp/catalog/` continua sendo a fonte do Backstage, e as entidades criadas pela CLI não aparecem nele.
- Projeção no Postgres (#172): a lista lê os CRDs direto, como o Environment.
- Ajuste dos comandos ilustrativos do deck (PR à parte).
