# IDP presentation port

Trazer a apresentação detalhada do IDP (v3 do repo de origem) para este repo público, sem referências à empresa de origem, como deck único. Cortes por público (negócio, engenharia) não são copiados: virão de filtro sobre a classificação `audiences` dos slides.

## Decisões

- Deck único: só a v3. `v1`, `v2`, `business` e `technical` ficam de fora; `technical` contribui só com os geradores e SVGs que a v3 usa.
- Snapshot sem histórico git da origem.
- Ato `where-we-are` reescrito com o estado real do wasp-idp (EKS via Crossplane hub-and-spoke, Backstage, ADRs; próximos passos = board #6).
- Ferramentas Azure no catálogo/landscape mantidas por ora; troca para AWS em issue separada.
- GitHub Pages no mesmo PR.
- `source/` fora: deck base interno e PDFs com copyright; references passam a citar a URL pública de cada relatório.

## Estrutura de destino

```
docs/presentation/
├─ README.md            o que é, como renderizar, filtro futuro
├─ CONTRIBUTING.md      sem marketplace da empresa, sem seções de deck derivado
├─ render-outline       YAML → HTML (sem mudança de código)
├─ idp.yaml / idp.html  ex-v3
├─ snippets/            catalog-info.yaml, app-spec.yaml
├─ diagrams/            landscape/ + journey/ (build.py + SVGs gerados)
├─ catalog/idp.yaml     arquitetura de referência como entidades Backstage
└─ references/          PROMPT.md + tópicos sanitizados
```

O índice interno do deck (tecla `I`, agenda por `parts`) continua: vem do `render-outline` + bloco `parts:` do `idp.yaml`. Sai só a home multi-deck (`render-index`), que volta junto com o filtro por `audiences` quando houver mais de um corte.

Fora: `make-yaml`, `render-index`, variantes exploratórias da landscape (`01-…`, `02*-…`, `04-…`, `09-…`, `cli-examples.html`, `deck.html`, `index.html`), `source/`, `__pycache__`.

## Passos

1. Issue no board #6 com `Status`; branch `feat/<n>-idp-presentation`.
2. Copiar arquivos para a estrutura acima; ajustar caminhos no YAML (`../technical/landscape/…` → `diagrams/landscape/…`, `snippets/…`) e nos `build.py` (saída).
3. Sanitizar `idp.yaml` (editorial, sem subagente):
   - `problem`: o slide do modelo anterior vira cenário genérico (infra centralizada, pedir é burocrático, ambiente caro para quem só quer um serviço); `delivery-friction`, `cognitive-load` perdem a menção.
   - Exemplo de catálogo (slide da árvore, `idea-to-product`, `declare-*`, `journey-plan*`): nomes da origem → exemplo de `idp/catalog` (domain `communication`, `greeter`/`notifier`); snippets alinhados.
   - `journey/build.py`: app e domínio da origem → `greeting-api` e `platform.example.com`; regerar SVGs.
   - Menções pontuais (`platform-facade`, `release-rings`, `token-finops`, `ai-gateway`, `idle-environments`, `north-star-metric`, `guardrails`, `single-sign-on`, `one-issuer`, `cli-example`, `golden-signals`): reescrever a frase.
   - `where-we-are`: reescrever com o wasp-idp.
   - Remover nomes de pessoas das notas.
4. References: entram como estão as sem menção; ~20 com menção pontual vão em fan-out para 2 subagentes Sonnet (mesmo bloco de regras, lista explícita, retorno de uma linha). Fora: as 6 referências de estratégia, PRDs, times e compliance internos. `PROMPT.md` reescrito à mão (decisões da empresa saem; entra "deck único, cortes por filtro").
5. Pages: workflow `presentation-pages.yaml` adaptado para um deck (sem `render-index`; `index.html` = o deck); habilitar Pages no repo (`build_type: workflow`).
6. Verificação central:
   - grep de tokens proibidos (empresa, produtos internos, nomes de pessoas, domínios internos, account IDs) em todo `docs/presentation/`, incluindo HTML e SVG;
   - links das references resolvem; nenhuma reference órfã;
   - `render-outline idp.yaml` sem erro; `build.py` reproduz os SVGs commitados;
   - revisão visual no Chrome.
7. Uma linha no `HANDOFF.md`; PR via `gh pr create`.

## Fora do escopo (issues separadas)

- Filtro por `audiences` no `render-outline` (gera cortes por público a partir do deck único).
- Troca das ferramentas Azure por AWS no catálogo e landscape.
