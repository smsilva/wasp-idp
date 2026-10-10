# Backstage relations

Como as entidades do catálogo se ligam: qual campo do YAML cria cada relação, entre quais kinds, e o que isso permite perguntar ao catálogo. Complementa [`backstage-catalog.md`](backstage-catalog.md), que define cada entidade e mostra as árvores de exemplo.

Fontes (lidas em 2026-10-08):

- System model: <https://backstage.io/docs/features/software-catalog/system-model>
- Well-known relations: <https://backstage.io/docs/features/software-catalog/well-known-relations>
- Descriptor format: <https://backstage.io/docs/features/software-catalog/descriptor-format>

## A ideia central

O dev declara **uma direção** no YAML da própria entidade (`spec.owner`, `spec.system`, `spec.dependsOn`…), e o catálogo gera o **par** de relações: `ownedBy` em quem declarou e `ownerOf` no dono. Ninguém edita o YAML do outro lado — o time dono não precisa listar o que possui, o banco não precisa listar quem depende dele.

Consequência para a narrativa: o grafo inteiro (quem depende de quem, quem é dono do quê) sai de arquivos pequenos, cada um junto do próprio código e mantido pelo próprio dono.

## Três eixos

As relações se organizam em três perguntas diferentes:

| Eixo | Pergunta | Relações |
|---|---|---|
| **Pertencimento** | Faz parte de quê? | `partOf` / `hasPart` (Component, API, Resource → System → Domain; Component → Component; Domain → Domain) |
| **Uso em runtime** | Do que precisa para funcionar? | `providesApi` / `apiProvidedBy`, `consumesApi` / `apiConsumedBy`, `dependsOn` / `dependencyOf` |
| **Responsabilidade** | Quem responde por isso? | `ownedBy` / `ownerOf`, `memberOf` / `hasMember`, `parentOf` / `childOf` |

O pertencimento é a árvore (negócio em cima, implementação embaixo); o uso em runtime são arestas que **cruzam** a árvore; a responsabilidade liga cada nó a pessoas.

## Campo → relação

| Campo no YAML | Em quais kinds | Aponta para | Relação gerada | Obrigatório |
|---|---|---|---|---|
| `spec.owner` | Component, API, Resource, System, Domain | User ou Group | `ownedBy` / `ownerOf` | **sim** |
| `spec.system` | Component, API, Resource | System | `partOf` / `hasPart` | não |
| `spec.domain` | System | Domain | `partOf` / `hasPart` | não |
| `spec.subcomponentOf` | Component | Component | `partOf` / `hasPart` | não |
| `spec.subdomainOf` | Domain | Domain | `partOf` / `hasPart` | não |
| `spec.providesApis` | Component (a doc diz "typically from a Component") | API | `providesApi` / `apiProvidedBy` | não |
| `spec.consumesApis` | Component | API | `consumesApi` / `apiConsumedBy` | não |
| `spec.dependsOn` | Component, Resource | Component ou Resource | `dependsOn` / `dependencyOf` | não |
| `spec.dependencyOf` | Component, Resource | Component ou Resource | `dependencyOf` / `dependsOn` (declarado do outro lado) | não |
| `spec.memberOf` | User | Group | `memberOf` / `hasMember` | sim |
| `spec.parent` / `spec.children` | Group | Group | `childOf` / `parentOf` | `children` sim |

Definições literais da doc:

- `ownedBy`/`ownerOf`: "An ownership relation where the owner is usually an organizational entity (User or Group), and the other entity can be anything."
- `partOf`/`hasPart`: "a component belongs to a larger component; a component, API or resource belongs to a system; that a system is grouped under a domain."
- `dependsOn`/`dependencyOf`: "A general expression of being in need of that other entity for an entity to function."
- `providesApi`/`consumesApi`: "express that a component exposes an API" / "consumes an API".

## Duas regras que explicam o desenho

- **`owner` é o único campo obrigatório em todo kind de software.** Pertencimento e dependências são opcionais; dono não. Liga direto ao slide `catalog-ownership` ("o que existe e quem é dono").
- **Quando há contrato, a ligação passa pela API.** `providesApis` de um lado e `consumesApis` do outro, com a API como entidade própria no meio; `dependsOn` fica para o que é usado diretamente (um banco, uma fila, um componente interno). Essa divisão é leitura nossa do modelo — a doc não a formula como regra —, mas é o que sustenta a API como fronteira: "Form an important (maybe the most important) abstraction that allows large software ecosystems to scale."

## O System esconde o que está dentro

- System: "A collection of resources and components that exposes one or several public APIs." A doc destaca que ele esconde Resources e APIs privadas dos consumidores, o que deixa o dono evoluir a implementação sem afetar quem consome; tipicamente "at most a handful of components".
- Visibilidade da API: "public (making them available for any other component to consume), restricted (only available to an allowed set of consumers), or private" (só dentro do próprio System).
- Domain: "share terminology, domain models, metrics, KPIs, business purpose, or documentation, i.e. they form a bounded context"; pode ter subdomínios (`subdomainOf`).
- Exemplo da própria doc: um System de gestão de playlists com serviços de atualização e consulta, um banco, e expondo uma API RPC, snapshots de dataset e um event stream.

## No catálogo real deste repo

Fonte: `idp/catalog/communication/catalog-info.yaml`.

| Campo | Exemplo |
|---|---|
| `owner` | `greeting-api` → `group:default/team-alpha` |
| `system` | `greeting-api` → `greeter` |
| `domain` | `greeter` → `communication` |
| `dependsOn` | `greeting-api` → `greeting-db`, `greeting-events`, `greeting-avatars` |
| `providesApis` | `greeting-api` → `greeting-http` |
| `children` | Groups |

Par completo de API já presente: `greeting-api` **provê** `greeting-http` — o exemplo pronto de "contrato no meio" sem inventar nada; um consumidor entra com `consumesApis`. Não há Users (só Groups), então `memberOf` não aparece.

## Como pode virar slide (não decidido)

Ideias para quando a curadoria pedir; nenhuma está no outline.

- Uma tela com os três eixos (pertencimento, uso, responsabilidade) sobre a árvore do `greeter`.
- "Declara um lado, o catálogo gera os dois": o trecho `owner` + `system` do `catalog-info.yaml` ao lado das relações geradas na página da entidade.
- O par `greeting-api` → `greeting-http` (com um consumidor via `consumesApis`) como exemplo de API como fronteira.
- Encaixe provável: entre `entity-domain` e `spotify-tree` (depois das entidades, antes da árvore), ou dentro do tópico "Declaring an app", junto de `declare-ownership`/`declare-apis`/`declare-dependencies`.
