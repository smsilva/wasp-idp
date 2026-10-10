# DORA AI report

- Fonte: DORA / Google Cloud, "State of AI-assisted Software Development 2025", v. 2025.2, PDF público em <https://services.google.com/fh/files/misc/2025_state_of_ai_assisted_software_development.pdf> (lido em 2026-10-07; página de apresentação em <https://dora.dev/dora-report-2025/>). Páginas abaixo = número impresso no rodapé do PDF.
- Fonte: DORA / Google Cloud, "DORA AI Capabilities Model", v. 2025.1, PDF público em <https://services.google.com/fh/files/misc/2025_dora_ai_capabilities_model.pdf> (lido em 2026-10-07). Companion do relatório 2025.
- Fonte: DORA / Google Cloud, "Accelerate State of DevOps 2024", v. 2024.3, PDF público em <https://services.google.com/fh/files/misc/2024_final_dora_report.pdf> (lido em 2026-10-07; página em <https://dora.dev/research/2024/>).
- Fonte: Nathen Harvey e Derek DeBellis, "Announcing the 2025 DORA Report", Google Cloud Blog, 2025-09-23, <https://cloud.google.com/blog/products/ai-machine-learning/announcing-the-2025-dora-report> (lido em 2026-10-07).
- Fonte: Jessica Baolin e Nathen Harvey, "Balancing AI tensions: Moving from AI adoption to effective SDLC use", dora.dev, 2026-03-10, <https://dora.dev/insights/balancing-ai-tensions/> (lido em 2026-10-07).

## Metodologia (2025)

- Survey: "a global survey conducted between June 13 and July 21, 2025" (relatório 2025, p. 4, Key findings).
- Amostra: "This year, a total of 4,867 respondents answered our survey" (p. 103, Demographics and firmographics). No resumo executivo: "more than 100 hours of qualitative data and survey responses from nearly 5,000 technology professionals" (p. 3).
- Entrevistas: "In total, we interviewed 78 participants", de forma contínua "from July 2024–July 2025" (p. 115, Methodology).
- Survey em quatro fluxos atribuídos aleatoriamente: "AI", "Platform engineering", "Sociocognitive aspects", "AI capabilities" (p. 114). Cada respondente viu só um fluxo, então nem toda pergunta tem os 4.867.
- Os efeitos são estimativas bayesianas padronizadas "with 89% credible intervals" (Figure 1, p. 4; Figure 28, p. 38): o relatório 2025 dá **direção e tamanho padronizado**, não porcentagens como o de 2024.
- Instabilidade em 2025 = "Change fail rate" + "Rework rate"; throughput = "Lead time for changes", "Deployment frequency", "Failed deployment recovery time" (p. 13, Software delivery performance factors).

## Metodologia (2024)

- "This year, nearly 3,000 working professionals from a variety of industries around the world shared their experiences" (relatório 2024, p. 91, Demographics and firmographics). Histórico: "roughly 39,000 professionals" ao longo do programa.

## IA, throughput e instabilidade (2025) — a fonte primária do slide

- "AI adoption now improves software delivery throughput, a key shift from last year. However, it still increases delivery instability. This suggests that while teams are adapting for speed, their underlying systems have not yet evolved to safely manage AI-accelerated development." (p. 4, Key findings).
- A pessoa com mais adoção de IA reporta "Higher levels of software delivery instability" e "Higher levels of software delivery throughput" (p. 38, The results this year).
- "AI's relationship with software delivery throughput has turned from negative to positive" (p. 42, Changes in last year's patterns suggest adaptation).
- "it continues its detrimental relationship with software delivery stability" (p. 43, Conclusion).
- Blog: "AI accelerates software development, but that acceleration can expose weaknesses downstream. Without robust control systems, like strong automated testing, mature version control practices, and fast feedback loops, an increase in change volume leads to instability." (Google Cloud Blog, 2025-09-23, seção "Key findings from the 2025 report").
- dora.dev (2026-03-10): "higher AI adoption is associated with an increase in both software delivery throughput and software delivery instability"; mecanismo proposto: "the time saved in creation is frequently re-allocated to auditing and verification".

## IA e entrega em 2024 (números literais)

- Seção "AI is hurting delivery performance", Figure 10 (relatório 2024, p. 39): "If AI adoption increases by 25%…" → "Delivery throughput -1.5%", "Delivery stability -7.2%".
- "We see that the effect on delivery throughput is small, but likely negative (an estimated 1.5% reduction for every 25% increase in AI adoption). The negative impact on delivery stability is larger (an estimated 7.2% reduction for every 25% increase in AI adoption)." (p. 40).
- Hipótese do DORA: "since AI allows respondents to produce a much greater amount of code in the same amount of time, it is possible, even likely, that changelists are growing in size. DORA has consistently shown that larger changes are slower and more prone to creating instability." (p. 40).

## AI as amplifier

- "AI's primary role in software development is that of an amplifier. It magnifies the strengths of high-performing organizations and the dysfunctions of struggling ones." (relatório 2025, p. 3, Key takeaway).
- "Without this foundation, AI creates localized pockets of productivity that are often lost to downstream chaos." (p. 3).
- Blog: "AI doesn't fix a team; it amplifies what's already there." (Google Cloud Blog, seção "AI, the great amplifier").
- Adoção: "The majority of survey respondents (90%) use AI as part of their work and believe (more than 80%) it has increased their productivity. Yet a notable portion (30%) currently report little to no trust in the code generated by AI" (p. 4).

## DORA AI Capabilities Model (7 capacidades)

Lista literal (AI Capabilities Model, p. 4, Executive summary):

1. "Clear and communicated AI stance" — "Ambiguity creates risk. A clear policy provides the psychological safety needed for effective experimentation."
2. "Healthy data ecosystems" — "The benefits of AI are significantly amplified by high-quality, accessible, and unified internal data."
3. "AI-accessible internal data" — "Connecting AI to your internal documentation and codebases moves it from a generic assistant to a specialized expert."
4. "Strong version control practices" — "As AI increases the velocity of change, version control becomes the critical safety net that enables confident experimentation."
5. "Working in small batches" — "This discipline counteracts the risk of AI generating large, unstable changes, ensuring that speed translates to better product performance."
6. "User-centric focus" — "A focus on user needs is essential to ensure that AI-accelerated teams are moving quickly in the right direction."
7. "Quality internal platforms" — "A platform provides the automated, secure pathways that allow AI's benefits to scale across the organization."

## Plataforma como pré-condição da IA (2025)

- "90% of organizations have adopted platform engineering, making a high-quality internal platform the essential foundation for AI success." (relatório 2025, p. 4).
- "Our data shows that 90% of organizations have adopted at least one platform, with 29% of organizations now using a multi-platform environment." e "76% of organizations have at least one dedicated platform team" (p. 67, The platform landscape).
- "AI adoption has a negligible effect on organizational performance when platform quality is low, but when platform quality is high, the effect is strong and positive." (p. 71, The strategic imperative; Figure 49).
- "With a high degree of certainty, we found that AI adoption's impacts depend on organizations having quality internal platforms." (p. 62, Quality internal platforms). Mas também: "respondents experience more friction in organizations with quality internal platforms" (p. 62).
- Qualidade da plataforma = "a single score, indicating how many of 12 characteristics a respondent indicates their internal platforms have" (p. 62).
- "An investment in AI without a corresponding investment in high-quality platforms is unlikely to yield significant returns at the organizational level." (p. 72).
- Ganhos de produtividade individuais "are often lost to downstream disorder, swallowed by bottlenecks in testing, security reviews, and complex deployment processes." (AI Capabilities Model, p. 59, Quality internal platforms).
- Plataforma também aumenta instabilidade: "a better platform is associated with a small but credible increase in software delivery instability, meaning a higher change failure rate and increased rework." Leitura do DORA: "a manageable trade-off for the significant gains in performance" (relatório 2025, p. 70).
- "Experience gap": capacidades técnicas (confiabilidade, segurança) bem avaliadas; "acting on feedback" e "how well tasks are automated" ficam atrás (p. 67). "the capability most correlated with a positive user experience is providing clear feedback to tasks" (p. 69).
- Antipadrões nomeados: "Build it and they will come", "The ticket-ops trap", "The ivory tower platform" (p. 68).

## Platform engineering em 2024 (números literais)

- "we found that 89% of respondents are using an internal developer platform" (relatório 2024, p. 50).
- "Internal developer platform users had 8% higher levels of individual productivity and 10% higher levels of team performance. Additionally, an organization's software delivery and operations performance increases 6% when using a platform. However, these gains do not come without some drawbacks. Throughput and change stability saw decreases of 8% and 14%, respectively" (p. 49).
- Developer independence: "a 5% improvement in productivity when users of the platform are able to complete their tasks without involving an enabling team" (p. 51). Plataforma obrigatória: "there was a 6% decrease in throughput" para quem deve "exclusively use the platform" (p. 53).

## Value stream management (2025)

- "Value stream management (VSM), the practice of visualizing, analyzing, and improving the flow of work from idea to customer, acts as a force multiplier for AI, ensuring that local productivity gains translate into measurable improvements in team and product performance." (relatório 2025, p. 4).
- "Without VSM, AI risks creating localized efficiencies that are simply absorbed by downstream bottlenecks, delivering no real value to the organization as a whole." (p. 77). Achados declarados: "VSM drives team performance", "VSM leads to more valuable work", "VSM improves product performance" (p. 77).
- Observação: o p. 77 formula "VSM moderates the relationship between AI adoption and organizational performance" como **hipótese** ("We hypothesize"); o resumo executivo (p. 4-5) o trata como achado.

## Não verificado

- **Edição 2026 do State of AI-assisted Software Development**: não encontrada; `dora.dev/research/` lista até 2025 (lido em 2026-10-07).
- **"ROI of AI-assisted Software Development" (2026)**: lido na íntegra em 2026-10-07 — ver [`dora-roi-ai.md`](dora-roi-ai.md). Os números citados por terceiros (J-curve, CFR de 5% para 6%, ROI de 39%) estão lá, mas são premissas ilustrativas da calculadora, não achados.
- O tamanho do efeito de IA sobre instabilidade em 2025 só existe em gráfico (Figure 28, escala padronizada ~-0,05 a 0,20); não há número literal no texto — não citar porcentagem para 2025.
- Lista das 12 características de plataforma de qualidade (Appendix do relatório 2025): não lida.

## Uso na apresentação

- Slide `ci-bottleneck`: trocar a fonte secundária (artigo patrocinado da Signadot, `sandbox-routing.md`) pelo relatório 2025, p. 4 ("improves software delivery throughput… still increases delivery instability") e, como mecanismo, o blog ("an increase in change volume leads to instability") e o AI Capabilities Model p. 59 ("swallowed by bottlenecks in testing, security reviews"). Contraste 2024→2025: throughput passou de -1,5% para positivo; estabilidade seguiu negativa (-7,2% em 2024).
- Slides de plataforma como pré-condição da IA (`platform-readiness`, `rebuild-platform`): p. 71 ("negligible effect… when platform quality is low"), p. 72 ("An investment in AI without a corresponding investment in high-quality platforms…"), 90% / 76% / 29% (p. 67) e a 7ª capacidade do AI Capabilities Model. Ressalva honesta para as notas: plataforma também traz mais fricção (p. 62) e um pouco mais de instabilidade (p. 70; 2024: -8% throughput, -14% change stability).
- `dora-metrics`: em 2025 o DORA mede instabilidade por "Change fail rate" + "Rework rate" e moveu "Failed deployment recovery time" para throughput (p. 13) — conferir contra `dora-metrics.md`.
