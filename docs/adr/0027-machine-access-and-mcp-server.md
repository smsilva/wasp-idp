# Machine access and an MCP server over the Platform API

**Status:** Aceito (2026-10-13)

## Contexto

Hoje só pessoas usam a Platform API: a CLI e o Backstage autenticam um humano no Keycloak (ADR 0021) e chamam `/v1/*`. Sistemas (pipelines, outros serviços) e agentes de IA também precisam operar a plataforma, os sistemas por conta própria e os agentes em nome de alguém (#217).

O `Principal` da API (`platform/api/src/platform_api/auth.py`) carrega `sub`, `email` e os grupos; `Principal.actor` grava `sub (email)` no journal e não sabe qual client emitiu o token. Não existe recurso de operação nem `Idempotency-Key`: `POST`/`DELETE /v1/environments` respondem `202` e o cliente acompanha pelo `get`.

A CLI (`cli/src/wasp_platform`) já tem um cliente HTTP (`PlatformClient`) com catálogo, components, ambientes, builds, workloads e sinais, e um login com refresh automático (`auth.access_token`).

## Decisão

**Sistemas e agentes usam a mesma Platform API, com identidade própria; agentes chegam a ela por um MCP server que é um adaptador fino, com toolsets habilitáveis.**

- **Fronteira única.** Sistemas e agentes consomem `/v1/*`, como a CLI e o Backstage. Nada fala direto com kube API, Crossplane, ArgoCD ou Forager, e não existe uma "API de integração" separada.
- **Keycloak emite tokens, a Platform API decide autorização** (ADR 0021). Service accounts e grants de agentes são recursos da plataforma, não clients soltos no realm.
- **Dois tipos de identidade não humana:** service account, que age por conta própria (`client_credentials`, #218), e agente em delegação, com `sub` = usuário e o agente identificado como client (`azp`, #219).
- **Delegação, não impersonação.** A permissão efetiva de um agente em nome de alguém é a interseção das permissões do usuário com os scopes concedidos ao agente, e o journal registra os dois.
- **MCP como adaptador fino.** Toda tool chama uma rota `/v1/*`; autorização, validação e auditoria continuam na API. Um único server com **toolsets** habilitáveis (`--toolsets core,environments`), para o agente carregar só as tools que usa. Quebrar em servers separados só se ciclos de vida ou donos divergirem; as tools não mudam.
- **Somente leitura por padrão.** Cada tool declara as anotações do MCP (`readOnlyHint`, `destructiveHint`, `idempotentHint`); tools de escrita só são registradas quando o server sobe com `--allow-writes`.
- **Python, reaproveitando a CLI.** O server é um projeto `uv` próprio (`platform/mcp/`) que depende de `wasp-platform` por path e chama o `PlatformClient`; não há segundo cliente HTTP.

### Fases

- **Fase 1 (#222):** server local, transporte **stdio**, iniciado pelo MCP client do agente. Autentica com **o login da CLI do próprio usuário** (`auth.access_token`), sem client novo no Keycloak. Toolset `core` com `whoami` (`/v1/me`); os toolsets de domínio vêm em seguida (#224 ambientes, #223 catálogo).
- **Fase 2 (depois de #219 e #221):** transporte **Streamable HTTP** no cluster, subido pelo `platform init`; autorização conforme a especificação do MCP (OAuth 2.1) com o Keycloak como authorization server e o client de agente da #219, de modo que o token chega com `sub` + `azp`. Tools de escrita ganham `Idempotency-Key` e `operation_get` (#221).

**Exceção aceita só na fase 1:** com o token do usuário, o journal registra o humano e não distingue o agente. Isso contraria a delegação acima e acaba na fase 2.

## Alternativas consideradas

- **Uma API de integração separada para sistemas e agentes.** Duplicaria autorização e auditoria e criaria um segundo contrato para manter. Rejeitada.
- **Um MCP server por control plane (catálogo, ambientes, nuvem).** Tem o mesmo efeito de carregar só parte das tools, mas multiplica processos, configuração e autenticação no agente. Rejeitada enquanto as tools tiverem o mesmo dono e o mesmo ciclo de vida.
- **Subcomando `platform mcp` na CLI.** Instala junto, mas leva o SDK do MCP para todo usuário da CLI e prende a fase 2 (um serviço no cluster) ao pacote da CLI. Rejeitada.
- **Esperar #219 e #221 para começar o MCP.** Mantém a auditoria correta desde o primeiro dia, mas adia a demo da plataforma para agentes. Rejeitada em favor das fases, com a lacuna registrada acima.

## Consequências

- O agente da fase 1 tem exatamente o poder do usuário logado e é auditado como ele; só os toolsets e o `--allow-writes` limitam o que ele vê.
- Toda rota nova da API ganha uma tool só quando um toolset a pede; o server não reflete o OpenAPI automaticamente.
- Os toolsets dependem do `PlatformClient`: uma mudança de assinatura nele quebra os testes do server, que roda contra o mesmo pacote.
- Sem Deployment na fase 1, o MCP não aparece em `platform status` (ADR 0039); na fase 2 ele entra com as labels de provider.
