# Catalog Import — Design

Issue [#190](https://github.com/smsilva/wasp-idp/issues/190). Depende da fatia 1 do catálogo ([#191](https://github.com/smsilva/wasp-idp/issues/191), spec `2026-10-10-platform-catalog-design.md`) e do [ADR 0023](../../adr/0023-platform-catalog-ownership.md).

## Contexto

O catálogo da plataforma (Domain, System, Resource) é gerido pela Platform API e pela CLI, uma entidade por comando. Quem adota a plataforma já tem um catálogo no formato Backstage (`apiVersion: backstage.io/v1alpha1`), em arquivos ou num Backstage; neste repo, em `idp/catalog/`. Recadastrar entidade por entidade desestimula a adoção, e o ADR 0023 já diz que `idp/catalog/` vira carga inicial, importada por `platform catalog import`.

## Decisões

### 1. O plano é calculado pela API, a partir dos documentos Backstage crus

A CLI só lê os arquivos YAML e envia os documentos como estão. A conversão Backstage → plataforma, os `skip` com motivo, a validação de referências e a autorização ficam na API, num módulo próprio (`platform_api/catalog_import.py`), separado do `catalog.py`. O Backstage e os agentes chamam a mesma rota e recebem o mesmo plano, sem reimplementar a conversão.

### 2. Rota única, com `dryRun` e impressão digital do plano

`POST /v1/catalog/import`, com `dryRun: true` para revisar e `dryRun: false` para aplicar. A revisão devolve um `planHash`; o apply reenvia os mesmos documentos com esse `planHash`, a API recalcula o plano e recusa com `409` se o hash não bater. A API não guarda estado entre as duas chamadas e aplica exatamente o que foi revisado. Sem `planHash` (CLI com `--yes`), o apply aceita o plano do momento.

Descartados: plano salvo no servidor com id (armazenamento e expiração sem ganho sobre o hash) e a CLI executando create/update um a um (exigiria rota pública de update e reimplementação em cada cliente).

### 3. Plano com `error` ou `forbidden` não aplica nada

Referência quebrada, campo obrigatório faltando e falta de permissão aparecem no plano, por entidade, e bloqueiam o import inteiro. Não existe aplicação parcial do que pode ser aplicado: um filho aplicado sem o pai deixaria referência pendurada.

### 4. Autorização por entidade, com as mesmas regras das rotas existentes

- **Create:** Domain só `platform-admins`; System e Resource, qualquer usuário (como `POST /v1/catalog/{plural}`).
- **Update:** Domain só `platform-admins`; System e Resource só quem criou (anotação `created-by`) ou `platform-admins` — a regra do delete (`is_owner_or_admin`).
- **`unchanged`** não exige permissão: um não admin importa arquivos com Domains que já existem iguais.

Quem não pode recebe `forbidden` no item, com o motivo, e o plano não aplica (decisão 3).

### 5. System sem `domain` é erro, não Domain inventado

A plataforma exige `domain` em System; o Backstage não. O import marca `error` em `spec.domain` com a sugestão de declarar o Domain no arquivo. Não existe `--default-domain` nem Domain criado em silêncio: os dois criam uma segunda verdade, divergente do arquivo. No mesmo PR, `idp/catalog/platform.yaml` ganha o Domain `platform` (owner `group:default/team-platform`) e o System `platform` passa a ter `domain: platform`.

### 6. O arquivo é a verdade do que ele declara

Um update grava o spec convertido do arquivo, inteiro: um campo ausente no arquivo (por exemplo `description`) é removido da entidade, e o diff do plano mostra a remoção. O update pode trocar o pai (`parent`, `domain`, `system`), e a referência nova é validada como no create. Entidades da plataforma que não estão nos arquivos ficam como estão: o import não apaga.

### 7. Update só como operação interna do import

Não há `PUT /v1/catalog/{plural}/{name}` nem `platform catalog <kind> update` nesta issue. A escrita (`StateWriter.replace`), o journal (`action: "update"`) e a regra de autorização ficam prontos; expor a rota depois custa pouco.

### 8. Aplicação não transacional, convergente

O apply grava na ordem do plano e para no primeiro erro de escrita, informando o que já foi gravado. Não desfaz: rodar o import de novo converge, porque o que já foi gravado vira `unchanged`.

## API

### Requisição

```json
{
  "documents": [
    {"source": "idp/catalog/platform.yaml#2", "document": {"apiVersion": "backstage.io/v1alpha1", "kind": "System", "metadata": {"name": "platform"}, "spec": {"owner": "group:default/team-platform", "domain": "platform"}}}
  ],
  "dryRun": true,
  "planHash": null
}
```

- `source` é texto livre, para o plano dizer de onde veio cada item. A CLI manda o caminho relativo ao diretório atual e, em arquivo com vários documentos, a posição (`#2`, contando de 1).
- `dryRun` é `true` quando omitido: aplicar exige pedir explicitamente.
- No máximo 500 documentos por import; acima disso, `422`.

### Resposta

```json
{
  "items": [
    {"kind": "Domain", "name": "communication", "action": "create", "source": "idp/catalog/communication/catalog-info.yaml#1", "spec": {"owner": "team-alpha", "description": "..."}},
    {"kind": "Resource", "name": "greeting-db", "action": "update", "source": "...", "spec": {"...": "..."}, "changes": {"owner": ["team-beta", "team-alpha"], "description": ["old text", null]}},
    {"kind": "System", "name": "bookinfo", "action": "unchanged", "source": "..."},
    {"kind": "Component", "name": "greeting-api", "action": "skip", "source": "...", "reason": "lives in the repo catalog-info.yaml"},
    {"kind": "Domain", "name": "payments", "action": "forbidden", "source": "...", "reason": "creating a domain requires group 'platform-admins'"},
    {"kind": "System", "name": "orphan", "action": "error", "source": "...", "field": "spec.domain", "reason": "domain 'nowhere' not found"}
  ],
  "summary": {"create": 1, "update": 1, "unchanged": 1, "skip": 1, "forbidden": 1, "error": 1},
  "planHash": "sha256:...",
  "applied": false
}
```

- `changes` mapeia cada campo alterado para `[antes, depois]`; `null` é ausência.
- No apply, cada item gravado ganha `"applied": true`; o item que falhou ganha `"failed": "<motivo>"`; o `applied` do topo é `true` só se tudo foi gravado.

### Ações

| Ação | Quando |
|---|---|
| `create` | a entidade não existe na plataforma |
| `update` | existe, e algum campo do spec convertido difere (inclusive campo removido) |
| `unchanged` | existe e é igual |
| `skip` | documento que não é entidade Backstage (`apiVersion` fora de `backstage.io/*`, como um `mkdocs.yml` na pasta), kind não importado, ou `metadata.namespace` diferente de `default` |
| `forbidden` | o usuário não pode fazer o create ou o update (decisão 4) |
| `error` | entidade Backstage sem `metadata.name` ou sem `spec`, label inválido, owner fora do formato, campo obrigatório faltando, campo que o kind não aceita, referência quebrada, pai não importável, `kind/name` duplicado |

Motivos de `skip`:

| Kind | Motivo |
|---|---|
| sem `apiVersion: backstage.io/*` | `not a Backstage entity` |
| `Component`, `API` | `lives in the repo catalog-info.yaml` |
| `Group`, `User` | `identity lives in Keycloak (#186)` |
| `Template`, `Location` | `Backstage configuration, not a catalog entity` |
| outro | `not a catalog kind` |
| qualquer, com namespace ≠ `default` | `namespace '<ns>': the platform catalog has no namespaces` |

### Códigos

| Situação | Código | Corpo |
|---|---|---|
| `dryRun: true` | `200` | plano |
| apply sem `error`/`forbidden`, hash ok, tudo gravado | `200` | plano com `applied` |
| apply com `error` ou `forbidden` no plano | `422` | plano; nada gravado |
| apply com `planHash` divergente | `409` | plano novo; nada gravado |
| apply com falha de escrita no meio | `409` | plano com os itens já gravados e o que falhou |
| mais de 500 documentos, corpo inválido | `422` | erro padrão |

Os erros com plano no corpo usam o envelope padrão da API (`{"error": {"code", "message"}}`) com o plano em `error.plan`.

## Cálculo do plano

Em `platform_api/catalog_import.py`, função pura sobre os documentos, o estado (`StateReader`) e o `Principal`:

1. **Classificar:** documento que não é um objeto com `apiVersion` em `backstage.io/*` → `skip` (`not a Backstage entity`); kind fora de Domain/System/Resource → `skip`; namespace ≠ `default` → `skip`. Entidade Backstage sem `metadata.name` ou sem `spec` como objeto → `error`.
2. **Converter** para `EntityRequest`:
   - `metadata.name` → `name`; `metadata.description` → `description`;
   - `spec.owner`: `group:default/x`, `group:x` e `default/x` → `x`; texto sem prefixo segue como está; outro prefixo de kind (`user:...`) ou namespace diferente de `default` → `error` em `spec.owner`;
   - Domain: `spec.subdomainOf` → `parent`; System: `spec.domain` → `domain`; Resource: `spec.system` → `system`, `spec.type` → `type`;
   - demais campos do Backstage (`lifecycle`, `tags`, `links`, `dependsOn`, `annotations`, ...) são ignorados.

   A validação reaproveita `EntityRequest` (labels) e `spec_from` (campos aceitos e obrigatórios por kind); a mensagem de erro indica o campo no formato Backstage (`spec.domain`, `spec.subdomainOf`).
3. **Duplicados:** o mesmo `kind/name` em dois documentos → `error` nos dois, citando o outro `source`.
4. **Ordenar:** Domains em ordem topológica pelo `parent` (desempate por nome), depois Systems, depois Resources, por nome. Ciclo entre Domains → `error` em `spec.subdomainOf` nos envolvidos.
5. **Resolver referências** contra o que está no import sem erro mais o que já existe na plataforma. Pai ausente → `error` (`domain 'x' not found`); pai presente no import com `error` ou `forbidden` → `error` (`domain 'x' is not importable`), em cascata.
6. **Comparar** com o estado: inexistente → `create`; spec igual → `unchanged`; diferente → `update` com `changes`.
7. **Autorizar** `create` e `update` (decisão 4) → `forbidden`. Um `forbidden` propaga como no passo 5: os filhos de um Domain proibido viram `error`.

**`planHash`:** sha256 do JSON canônico (chaves ordenadas) da lista ordenada de itens `create` e `update`, cada um com `kind`, `name`, `action`, `spec` final e o `resourceVersion` lido (no `update`). Qualquer mudança no catálogo que afete o plano muda o hash.

## Aplicação

1. Recalcula o plano. Com `error` ou `forbidden` → `422`.
2. Com `planHash` e hash diferente → `409` (`catalog changed since the plan was made: review the plan again`).
3. Para cada `create`/`update`, na ordem: `journal.record(action, kind, name, spec, actor)` → escrita no kube → `journal.mark_applied`. O create usa o `manifest` do `catalog.py` (anotação `created-by`). O update lê o objeto, troca o `spec` e mantém `metadata` (inclusive `created-by` e `resourceVersion`).
4. Erro de escrita (`AlreadyExists`, `Conflict`, `NotFound`, erro do kube) → para, `409` com os itens gravados e o que falhou.

`StateWriter` ganha `replace(plural, body)`: `replace_namespaced_custom_object`, com `409` → `Conflict` e `404` → `NotFound`. O `FakeState` dos testes ganha o mesmo método, com checagem de `resourceVersion`. O RBAC da API (`platform/api/deploy/platform-api.yaml`) ganha o verbo `update` em `domains`, `systems`, `resources`.

Concorrência: não existe lock global. Dois imports simultâneos se protegem pelo `resourceVersion` de cada entidade e pelo `AlreadyExists`; o perdedor recebe `409` e um retry converge.

## CLI

```bash
platform catalog import <caminho>... [--dry-run] [--yes] [--output json]
```

1. **Leitura:** arquivos e pastas; pastas recursivas em `*.yaml` e `*.yml`, em ordem alfabética do caminho. `yaml.safe_load_all`, documentos vazios ignorados. YAML inválido falha antes de chamar a API, com arquivo e linha. Nenhum documento encontrado → erro `no YAML documents found in <caminhos>`.
2. **Revisão:** chama a API com `dryRun: true` e imprime o plano:

   ```text
   KIND       NAME             ACTION      DETAIL
   Domain     communication    create
   Domain     messaging        create      parent communication
   System     greeter          create      domain messaging
   Resource   greeting-db      update      owner: team-beta → team-alpha
   System     orphan           error       spec.domain: domain 'nowhere' not found (tmp/orphan.yaml#1)
   Group      team-alpha       skip        identity lives in Keycloak (#186)

   3 to create, 1 to update, 0 unchanged, 1 skipped, 1 error.
   ```

   `DETAIL` traz o pai no `create`, os `changes` no `update` (`campo: antes → depois`, `—` para ausência), e motivo e `source` em `skip`, `forbidden` e `error`.
3. **Decisão:**
   - `error` ou `forbidden` no plano → `fix the errors above; nothing was applied`, saída 1;
   - nada a gravar → `nothing to do`, saída 0;
   - `--dry-run` → para, saída 0;
   - `--yes` → aplica sem perguntar e sem `planHash`;
   - senão → `Apply? [y/N]`; sim reenvia com o `planHash` da revisão; não → `nothing was applied`, saída 0.
4. **Resultado:** `✓ 3 created, 1 updated`. No `409` por hash, imprime o plano novo e `the catalog changed since the review: run the import again`, saída 1. Na falha no meio, a tabela com os itens gravados e o que falhou, e `run the import again to converge`, saída 1.

`--output json` imprime o plano ou o resultado como a API devolveu e nunca pergunta: sem `--yes` equivale a `--dry-run`.

Cliente: `PlatformClient.import_catalog(documents, dry_run, plan_hash=None)`. `ApiError` passa a carregar o corpo da resposta (`error.plan`) para o comando exibir o plano nos `409`/`422`.

## Testes

**API** (`platform/api/tests/test_catalog_import.py`, `FakeState`):

- conversão: `subdomainOf`, `group:default/x` e `group:x`, owner `user:...` como erro, `description`, campos do Backstage ignorados;
- cada uma das seis ações, incluindo o update que remove `description` e o que troca o pai;
- ordem: subdomínio declarado antes do pai, Resource antes de System nos documentos, ciclo entre Domains;
- erros: referência quebrada com entidade e campo, cascata de pai não importável, duplicado, namespace ≠ `default`, mais de 500 documentos, System sem `domain`;
- autorização: Domain `forbidden` para não admin e cascata nos filhos; update de System alheio `forbidden`; Domain `unchanged` permitido a não admin;
- aplicação: `422` com erro no plano e nada gravado; `409` com hash divergente e nada gravado; falha no meio para e informa os gravados; journal com `create` e `update`; `created-by` preservado no update; segunda execução toda `unchanged`;
- ponta a ponta sobre os YAMLs reais de `idp/catalog/`.

**CLI** (`cli/tests/test_catalog_import.py`, `httpx.MockTransport`): pasta recursiva e arquivo com vários documentos, YAML inválido, nenhum documento, `--dry-run`, `--yes`, confirmação aceita e recusada, `--output json`, saída 1 com erro no plano, exibição do `409`.

## Documentação

- `cli/docs/walkthrough.md`: passo de import de `idp/catalog/` (revisão, confirmação, segunda execução com `nothing to do`).
- `cli/docs/index.md`: referência do comando.

## Aceite

No cluster local, depois de `platform init --target local` (API nova e RBAC com `update`):

1. `platform catalog import idp/catalog/` mostra 5 Domains (`bookstore`, `communication`, `messaging`, `notifications`, `platform`), 4 Systems (`bookinfo`, `platform`, `greeter`, `notifier`) e 8 Resources em `create`, e em `skip` os 3 Groups de `org.yaml` e os 2 `mkdocs.yml` (`not a Backstage entity`); aplica só depois da confirmação.
2. Rodar de novo: tudo `unchanged`, `nothing to do`.
3. Um arquivo temporário com um System apontando para um domain inexistente: o plano mostra o `error` com entidade e campo, e nada é aplicado.

## Fora de escopo

- Rota pública e comando de update (decisão 7).
- Sincronizar com remoção: entidades fora dos arquivos ficam como estão.
- Ler direto de um Backstage em execução (`/api/catalog/entities`); o import lê arquivos.
- `docs/presentation/catalog/idp.yaml`: material do deck, com owner `platform-team` divergente de `team-platform`; importá-lo criaria um owner paralelo. Não é carga inicial.
- Ligar owner a grupos do Keycloak (#186).
