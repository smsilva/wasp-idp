# The empathy gap

- Fonte: Tatiana Mikhaleva (fundadora da DevOps.Pink), "The empathy gap: Why your platform needs UX, not just APIs", platformengineering.org, 2026-03-23. <https://platformengineering.org/blog/the-empathy-gap-why-your-platform-needs-ux-not-just-apis>
- Artigo de opinião, não pesquisa: os números citados no texto ("most engineers report not knowing where to start"; salário de platform engineer "up to 27% more than DevOps") não trazem a fonte original — não usar na tela.

## Argumento

- IDPs falham por priorizar capacidade técnica sobre experiência de uso: muito investimento em infraestrutura, pouco no humano que a usa. O resultado é baixa adoção — o **empathy gap**.
- **Cognitive friction:** trocar de ferramenta e decifrar erro críptico quebra o estado de flow do dev.
- Golden paths devem remover barreiras, não acrescentar etapas.
- **Visual engineering:** dashboards, grafos e status claros em vez de log cru.

## Citações (literais)

- "We forget the most critical component in the stack. We forget the human being trying to use it."
- "A backend engineer should not need deep Kubernetes knowledge to get a URL for their service."
- "Clarity brings confidence. Confidence brings speed."
- "Ask: 'How does it feel?' If it feels like a struggle, nobody will use it."

## Recomendações

1. Investir em visual engineering e interfaces de dashboard.
2. Medir o sentimento do dev junto com as métricas DORA.
3. Ter product designers e frontend engineers no time de plataforma.
4. Tratar mensagem de erro e design da CLI como UX.
5. Priorizar a experiência do dev sobre a complexidade de features.

## Uso na apresentação

- Reforça "plataforma como produto" e a carga cognitiva do ato "problema".
- A citação da URL casa com a PoC: um pedido vira uma URL sem o dev saber Kubernetes.
- "CLI e mensagem de erro são UX" vale para o slide `many-clients`: a CLI não é cidadã de segunda classe.
- "Medir sentimento junto com DORA" casa com o caso Stone (NPS e funis — `stone-caravela.md`).
