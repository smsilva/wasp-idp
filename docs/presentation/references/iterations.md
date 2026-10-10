# Iterations

O deck é um só: `idp.yaml` (fonte única) → `./render-outline idp.yaml` gera `idp.html` (índice + uma página por slide). O HTML é artefato gerado, mas **versionado** para quem só revisa sem rodar o script: regerar antes de cada commit que mude o YAML, nunca editar à mão.

Cortes por público (negócio, engenharia) não são decks copiados: virão de um filtro sobre `audiences` e `dependsOn` ([`audiences.md`](audiences.md)).

| Fase | Foco | Status |
|---|---|---|
| Deck detalhado | IDP para humanos e agentes: problema, os 5 planes montados parte a parte na landscape, Platform API e clientes, jornada da ideia ao `curl`, ato `agentic` (camadas do AEP, Level 3, maturidade), MVP 1 e próximos passos | revisão |
| Filtro por público | `render-outline` gera cortes a partir de `audiences`, respeitando `dependsOn`; página inicial lista os cortes | — |
| Visual | `pptxgenjs`, paleta dark validada, QA visual | — |

## Passos (progressive build)

O `render-outline` expande cada slide em **passos**, um por reveal, no padrão dos `.odp` de referência da skill `presentation-prep` (duplicate slides). O elemento atual fica em branco, os anteriores esmaecem (`DIM`, `#6B7A8D`) e os seguintes ficam ocultos mas reservam o espaço, então nada muda de lugar entre passos. Todos os itens de um slide têm o mesmo tamanho; o destaque vem do contraste, não da escala.

- **Abertura de ato:** gerada a partir de `acts`, sem slide no YAML. Passo 1 mostra só o título do ato; passo 2 mostra o título esmaecido e a `question` em destaque. O primeiro ato (abertura) não ganha esse par.
- **Slide:** um passo por keyword de `screen`.
- **Diagrama (`diagram`):** um passo por parte de `reveal`. `show` fica em cor plena (o esqueleto: os planes vazios e as setas nunca se apagam), `dim` esmaecido (`opacity .32`: o conteúdo de planes já explicados), o resto oculto. Com `accumulate: true` as partes do mesmo `reveal` ficam acesas (a landscape vazia entra plane a plane). `start: empty` acrescenta um passo antes do primeiro `reveal` (o plane aparece vazio e depois as capacidades entram uma a uma). Parte com ponto (`dev.2`) herda o estado do grupo (`dev`) quando não é citada. Sem `reveal`, um passo com `show`.
- **Um passo só:** `animations: none` (abertura e fechamento: todas as keywords juntas) e slides com `code` (o foco já vem de `focus`).
- **Modo apresentação:** `P` ou "▶ apresentar" abre em tela cheia; ← → avançam, `F` alterna fullscreen, `Esc` sai. A URL `#present-N` abre direto no passo N.
- **Índice:** `I` (ou `[`) abre a lista de atos e slides sobre a apresentação, já posicionada no slide atual; ↑ ↓ (ou `j`/`k`, PageUp/PageDown) escolhem, Enter ou clique vai até lá, `I`/`Esc` fecha. Escolher um ato vai para a abertura dele.
- **Agenda (`parts`):** com o bloco `parts` no YAML (título, mensagem, `acts` agrupados e `items` com `go` para um ato ou slide), o índice vira a agenda: uma caixa por parte com número, nome, mensagem e itens, rolável quando é longa, com a parte atual em âmbar. Clicar num item vai para o primeiro conteúdo daquele ato ou slide. A agenda também volta como passo antes de cada parte, com a parte atual em destaque; `deck.agendaSteps: false` desliga isso em deck longo (o deck usa). `deck.meta` são os rótulos do canto direito. O `render-outline` valida que todo `acts` e todo `go` existem. Sem `parts`, o índice antigo continua — **todo deck novo tem `parts`** (formato em [`../CONTRIBUTING.md`](../CONTRIBUTING.md#formato-do-deck)).
- **Notas:** `N` liga/desliga o painel de notas (mensagem + notas, a escolha fica salva); `L` alterna a posição do painel entre a direita (default, aproveita a sobra lateral do slide 16:9) e embaixo. `S` abre uma janela do apresentador (`?presenter`, com notas) sincronizada com a principal: projete a principal sem notas e mantenha a do apresentador no seu monitor.

## Pré-requisitos da fase visual

- LibreOffice (`soffice`) é necessário para o QA visual (pptx → pdf → jpg). Instalação e demais dependências: [`../CONTRIBUTING.md`](../CONTRIBUTING.md).
- Link de fonte única no slide: `pptxgenjs` aceita `hyperlink: {url}` em texto — rodapé, fonte pequena, cor de baixo contraste sobre a paleta dark (ver `content-rules.md`).

## Revisão

- Ao gerar ou atualizar um HTML, **sempre abri-lo no Chrome** (não `code`), passando uma URL `file://` absoluta: `setsid google-chrome "file://<abs>/idp.html#<slide>" < /dev/null > /dev/null 2>&1 &`. Sem o `file://`, uma âncora `#slide` vira parte do nome do arquivo e o Chrome abre uma aba de "arquivo não encontrado". Com o Chrome já aberto, a página entra como **aba nova na janela existente** ("Opening in existing browser session").
