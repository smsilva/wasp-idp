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

`make mcp` na raiz instala `platform-mcp` no `PATH` (editable). `scripts/mcp-call whoami` sobe o server por stdio e chama uma tool; é o que o `scripts/demo/cli-smoke` usa.

## Toolsets

Um toolset é uma função em `src/wasp_platform_mcp/toolsets.py` que devolve `ToolSpec`s e entra em `TOOLSETS`. Tools de escrita levam `write=True` (e `destructive=True` quando apagam algo) e só são registradas com `--allow-writes`. Nome das tools: `<toolset>_<verbo>` (`environments_list`); as do `core` não têm prefixo. Como conectar um agente: `cli/docs/walkthrough/agents/connect.md`.
