# Install the CLI

```bash
cd wasp-idp/cli
uv sync
uv run platform --help
```

Para ter `platform` no `PATH`, na raiz do repo:

```bash
make cli
platform --help
```

O `make cli` roda `uv tool install --force --editable cli/`: a instalação aponta para este checkout, e rodar de novo em outro checkout troca para ele. `make cli-uninstall` remove.

!!! note
    Os exemplos abaixo usam `platform`. Sem o `uv tool install`, prefixe com `uv run`.
