# Biblioteca de templates (`wasp_templates`)

O código de templates de component (ADR 0024) usado por mais de um projeto: a CLI (`platform catalog template render`), a Platform API (validação dos `params` no `component create`) e o controller de criação de components (#204). Cada um a instala como dependência de caminho (`[tool.uv.sources]`, editable).

- `render.py`: Jinja2 sandboxed com os delimitadores do Backstage (`${{ … }}`) e o filtro `dump`; `copyWithoutRendering`; recusa symlinks e nomes que saem da pasta de saída; `annotate_origin` grava `platform.wasp.silvios.me/template: <nome>@<ref>` no `catalog-info.yaml`.
- `source.py`: `fetch` busca o conteúdo no ref registrado com o binário `git` (só `https`, `--` antes de repo e ref); `coerce` aplica os defaults e os tipos do JSON Schema aos `--param`.

Projetos que a usam e têm imagem (a API) buildam com `platform/` como contexto: `docker build --file api/Dockerfile platform`.

```bash
uv sync
uv run pytest
```
