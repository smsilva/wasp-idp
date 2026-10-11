# Biblioteca do Score (`wasp_score`)

O gate do `app-spec.yaml` (Score `score.dev/v1b1`) usado por mais de um projeto: o controller de build (`scm_github`, #206), que valida o Score do commit e grava o documento na `Version`, e a Platform API (`POST /v1/workload-specs:validate`, #291), que aplica o mesmo gate a um arquivo local. Cada um a instala como dependência de caminho (`[tool.uv.sources]`, editable).

- `check(text, resource_exists, resource_types)`: o documento, os erros (cada um com `field` e `reason`) e os resources declarados. Os erros vêm do YAML (aliases recusados), do schema, de tipos de resource que a plataforma não provisiona e de `id` fora do catálogo.
- `load(text)`: o `safe_load` sem aliases (`*nome`): poucos bytes de aliases aninhados viram milhões de nós em quem percorre o documento.
- `schemas/score-v1b1.json`: o schema vendorizado de `score-spec/spec`, nunca buscado em tempo de execução.
- `RESOURCE_TYPES`: os tipos de resource que a plataforma provisiona hoje.

Projetos que a usam e têm imagem buildam com `platform/` como contexto: `docker build --file api/Dockerfile platform`.

```bash
uv sync
uv run pytest
```
