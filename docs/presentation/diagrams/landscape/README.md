# Landscape

A landscape vazia (5 planes, sem ferramentas) que o deck monta parte a parte: moldura Platform API, clientes IDE/CLI/Portal/Agents com um exemplo cada.

Fonte única: `build.py`. Regerar com `python3 build.py` (escreve ao lado do script); nunca editar os SVG.

- `landscape.svg` — em partes (`<g data-part>`: planes, flow, dev, ind, res, obs, sec, api, clients), usada pelos slides `diagram` do `idp.yaml`.
- `cli.svg` — o terminal com exemplos da CLI, como diagrama de uma parte só (guardado, sem slide hoje).
- `python3 build.py --previews` gera também as variantes exploratórias do layout (`deck.html`, `index.html`, `NN-*.html`), ignoradas pelo git.
