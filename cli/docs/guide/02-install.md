# Install the CLI

```bash
cd wasp-idp/cli
uv sync
uv run platform --help
```

Para ter `platform` no `PATH`:

```bash
uv tool install --editable .
platform --help
```

!!! note
    Os exemplos abaixo usam `platform`. Sem o `uv tool install`, prefixe com `uv run`.
