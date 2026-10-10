# Audiences

**Filtro de slides por público: próximo passo.** O repo mantém um deck só, o detalhado; versões para outro público (negócio, engenharia) não são copiadas, saem de um filtro sobre esta classificação. Por ora os slides só são **classificados**.

- Campo `audiences` em cada slide do outline: públicos para os quais o slide é **mais relevante**. Sem o campo = relevante para todos.
- O HTML de revisão mostra essa classificação como tag ("mais relevante para"), sem esconder nada.
- Públicos:
  - `executive` — liderança: por que, quanto vale, o desenho.
  - `engineering` — devs que consomem a plataforma: como uso, o que declaro.
  - `platform` — time de plataforma: como funciona por dentro (orquestrador, IaC, guardrails).
- Abertura, transições de plane e fechamento ficam sem `audiences`.
- `dependsOn` registra o encadeamento do raciocínio; um filtro futuro deve respeitá-lo (não esconder um slide do qual outro visível depende).
