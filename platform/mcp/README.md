# platform-mcp

MCP server da Platform API para agentes de IA (ADR 0027). É um adaptador fino: cada tool chama uma rota `/v1/*` pelo `PlatformClient` da CLI (`cli/src/wasp_platform/client.py`), com o login de `platform login`. Autorização, validação e journal continuam na API.

Na fase 1 o transporte é **stdio** (o MCP client do agente sobe o processo) e o agente age com o token do usuário; Streamable HTTP e o client de agente do Keycloak chegam na fase 2 (#219, #221).

## Desenvolvimento

```bash
cd platform/mcp
uv sync
uv run pytest
uv run platform-mcp --help
```

`make mcp` na raiz instala `platform-mcp` no `PATH` (editable). `scripts/mcp-call whoami` sobe o server por stdio e chama uma tool; é o que o `scripts/test/cli-smoke` e o `scripts/test/cli-e2e` usam.

## Toolsets

Um toolset é uma função em `src/wasp_platform_mcp/toolsets.py` que devolve `ToolSpec`s e entra em `TOOLSETS`. Tools de escrita levam `write=True` (e `destructive=True` quando apagam algo) e só são registradas com `--allow-writes`. Todo argumento que entra no path de uma rota passa por `checked()`: o cliente resolve `..` e `/` em outra rota, e um `name` como `../../environments/demo` leria um ambiente (com kubeconfig) por uma tool de catálogo. Nome das tools: `<toolset>_<verbo>` (`environments_list`); as do `core` não têm prefixo. Como conectar um agente: `platform/docs/walkthrough/agents/connect.md`.
