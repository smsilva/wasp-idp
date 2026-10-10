# IDP presentation

Apresentação detalhada sobre Internal Developer Platform: o problema, os 5 planes montados parte a parte, a Platform API e seus clientes, a jornada da ideia ao `curl`, o que muda quando o usuário é um agente, e onde esta plataforma está hoje.

É um deck único. Versões para outro público saem de um filtro sobre a classificação `audiences` dos slides, não de cópias.

## Ver

```bash
cd docs/presentation
./render-outline idp.yaml
google-chrome "file://${PWD}/idp.html"
```

No HTML: `P` apresenta, `I` abre o índice (agenda por partes), `N` mostra as notas, `S` abre a janela do apresentador.

## Conteúdo

| Caminho | O que é |
|---|---|
| `idp.yaml` | O deck: atos, partes e slides (fonte única) |
| `idp.html` | Gerado pelo `render-outline`, versionado |
| `snippets/` | Código mostrado nos slides |
| `diagrams/` | Landscape e jornada: `build.py` + SVGs gerados |
| `catalog/idp.yaml` | Arquitetura de referência como entidades Backstage |
| `references/` | `PROMPT.md` (pedido, decisões, perguntas abertas) e um arquivo por fonte ou tópico |

Como contribuir: [`CONTRIBUTING.md`](CONTRIBUTING.md).
