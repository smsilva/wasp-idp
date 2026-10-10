# DORA metrics

- Fonte: DORA, "DORA's software delivery performance metrics", <https://dora.dev/guides/dora-metrics/> (página de 2026-01-05).

## As cinco métricas (literais)

Throughput:

- **Change lead time** — "The amount of time it takes for a change to go from committed to version control to deployed in production."
- **Deployment frequency** — "The number of deployments over a given period or the time between deployments."
- **Failed deployment recovery time** — "The time it takes to recover from a deployment that fails and requires immediate intervention."

Instability:

- **Change fail rate** — "The ratio of deployments that require immediate intervention following a deployment."
- **Deployment rework rate** — "The ratio of deployments that are unplanned but happen as a result of an incident in production."

- O modelo começou com **quatro** métricas ("four keys"); hoje são cinco. Failed deployment recovery time substituiu o antigo MTTR, e deployment rework rate é a quinta. Ao ouvir "four keys" em apresentações, é a versão antiga.

## Como não usar (guia do DORA)

- Não transformar a métrica em meta (vira jogo).
- Não medir sistema complexo por uma métrica só.
- Não comparar aplicações muito diferentes.
- Não deixar a métrica com um silo só: dev, ops e release compartilham.
- Não pôr times para competir; cada um compara consigo mesmo.
- Não investir mais em medir com precisão do que em melhorar.

## Uso na apresentação

- DORA mede a **entrega** dos times que usam a plataforma; a plataforma pode coletá-las e devolvê-las ao portal por plugin.
- Também medem a própria plataforma (o time de plataforma entrega mudanças no hub e nas Compositions).
- Complementam o time to 10th PR (`adoption-metrics.md`, onboarding) e o scorecard do *Platform as a Product* (MTTFD etc.).
- "Measure developer sentiment alongside DORA" (`empathy-gap.md`).
