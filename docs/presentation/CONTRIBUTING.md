# Contributing

Como preparar a sua máquina para contribuir com a apresentação do IDP. Feito para ser seguido por uma pessoa ou pelo Claude Code, do início ao fim.

## 1. Skills do Claude Code

A apresentação usa duas skills:

| Skill | O que faz | De onde vem |
|---|---|---|
| `presentation-prep` | Estrutura o conteúdo em slides (uma mensagem por slide, tela vs. notas, máx. 6 objetos) | Plugin pessoal; opcional — as regras que ela aplica estão em [`references/content-rules.md`](references/content-rules.md) |
| `pptx` | Gera e lê o `.pptx` | Plugin `document-skills` do marketplace oficial da Anthropic |

A `pptx` tem licença proprietária da Anthropic e não pode ser copiada para este repositório: ela vem do marketplace oficial.

```text
/plugin marketplace add anthropics/skills
/plugin install document-skills@anthropic-agent-skills

/reload-plugins
```

Para conferir, digite `/` numa sessão: `/pptx` deve aparecer.

## 2. Dependências de sistema

| Ferramenta | Usada em | Instalação (Ubuntu) |
|---|---|---|
| Python 3 + PyYAML | `render-outline` (todas as iterações) | `sudo apt install python3-yaml` |
| Google Chrome | Revisar o HTML | — |
| Node.js + `pptxgenjs` | Gerar o deck (fase visual) | `npm install --global pptxgenjs` |
| LibreOffice (`soffice`) | QA visual: pptx → pdf (fase visual) | `sudo apt install libreoffice-impress` |
| Poppler (`pdftoppm`) | QA visual: pdf → jpg | `sudo apt install poppler-utils` |
| `markitdown[pptx]` | Ler o texto de um `.pptx` | `pip install 'markitdown[pptx]'` |

Até a fase visual bastam Python, PyYAML e Chrome.

## 3. Conferir

```bash
cd docs/presentation
./render-outline idp.yaml
google-chrome "file://${PWD}/idp.html"
```

O `render-outline` imprime o caminho do HTML. Se houver erro de encadeamento (`dependsOn` apontando para um slide inexistente ou posterior), ele lista os erros e sai com código 1.

## 4. Fluxo de contribuição

1. Leia [`references/PROMPT.md`](references/PROMPT.md): pedido, decisões tomadas, perguntas em aberto e a tabela de tópicos.
2. Crie uma branch a partir de `origin/main`. Nunca commite na `main`.
3. Edite `idp.yaml`. Snippets de código mostrados nos slides ficam em `snippets/`; diagramas (SVG), em `diagrams/<nome>/`, com o gerador `build.py` ao lado.
   - **Versão para outro público:** não copie o deck. Classifique os slides com `audiences` e gere o corte pelo filtro (ver [`references/audiences.md`](references/audiences.md)).
4. Regere o HTML com `./render-outline idp.yaml` e confira no Chrome. O HTML é versionado: vai no mesmo commit que o YAML, e nunca é editado à mão. Diagramas: `python3 diagrams/<nome>/build.py`.
5. Contexto novo (uma fonte, um conceito, um dado) vira um arquivo em `references/` referenciado na tabela do `PROMPT.md`. Decisão nova vai em "Decisões tomadas".
6. Abra o PR.

## Campos do outline

| Campo | Obrigatório | Significado |
|---|---|---|
| `name` | sim | Slug estável do slide, usado pelo `dependsOn` |
| `act` | sim | Nome do ato (lista `acts` no topo do arquivo) |
| `message` | sim | A única ideia do slide, numa frase |
| `screen` | um dos três | Keywords que aparecem na tela (2–4 palavras cada) |
| `code` | um dos três | `{file, lines?, focus?}`: quadro de código estilo IDE; `focus` realça linhas e esmaece o resto |
| `diagram` | um dos três | SVG com partes `<g data-part="…">`. `show`: partes em cor plena (o esqueleto); `dim`: conteúdo já explicado, esmaecido; `reveal`: uma parte nova por passo. Partes anteriores do mesmo `reveal` esmaecem, salvo `accumulate: true` (o desenho cresce); `start: empty` abre com um passo antes do primeiro `reveal`; `empty` lista partes que só aparecem nesse passo (o `$` do terminal vazio). Parte `dev.2` herda o estado de `dev` quando não é citada |
| `heading` | não | Assunto do slide: sozinho no primeiro passo, depois no alto, esmaecido. Em `diagram`, ocupa a linha do tópico no cabeçalho |
| `topic` | não | Agrupa slides seguidos do mesmo assunto; a mudança de `topic` gera um passo de transição, salvo `divider: false` no slide |
| `source` | não | Rodapé "Source: …" do slide |
| `notes` | sim | O que o apresentador fala e não aparece na tela |
| `dependsOn` | não | Slides que precisam ter sido vistos antes (o encadeamento do raciocínio) |
| `audiences` | não | Públicos para os quais o slide é mais relevante (`executive`, `engineering`, `platform`). Base do filtro que gera versões por público |

## Formato do deck

Cabeçalho do `idp.yaml`:

```yaml
deck:
  name: idp-presentation
  title: …
  subtitle: …
  focus: …                 # uma linha: o que o deck é
  meta: [<rótulo>, …]      # canto direito da agenda
  agendaSteps: false       # true repete a agenda antes de cada parte; false em deck longo
  audience: For …          # público, discreto no primeiro slide (pequeno, cinza, maiúsculas)
acts:
- {name: opening, title: Opening}
- {name: <ato>, title: …, opening: false}   # o cabeçalho e a transição de tópico já dizem o ato
parts:                     # o índice (tecla I) no formato de agenda
- title: <Parte>
  message: …               # a frase da parte
  acts: [<ato>, …]         # atos agrupados, na ordem
  items:
  - {label: …, go: <ato ou slide>}
```

- **Toda parte cobre atos contíguos**, e todo ato fora de `parts` é só a abertura. O `render-outline` falha se um `acts` ou `go` não existir.
- **Diagrama que cresce ao longo do deck** (a landscape): um SVG só, gerado por script (`diagrams/landscape/build.py`), com uma parte por `<g data-part>`. Cada volta ao diagrama é um slide com `show` (o que já foi visto) e `reveal` (o que entra agora). Nunca editar o SVG à mão.
