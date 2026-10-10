# configure8: portal vs. platform

- Fonte: configure8, "Internal developer portal vs. internal developer platform: what's the difference and why both matter", 2023-03-29, sem autor declarado. <https://configure8.io/blog/internal-developer-portal-vs-internal-developer-platform-whats-the-difference-and-why-both-matter>
- **Material de vendor:** a configure8 vende portal (catálogo, self-serve actions, scorecards, gestão de custo). Mesma ressalva do guia da Port (`port-portal-guide.md`): é a visão de quem vende a interface.

## Definições (literais)

- Internal Developer Platform: "The collection of tooling built by platform engineers and used by developers. It is often a heterogeneous tool chain stitched together in a way to minimize cognitive load for developers without abstracting away important meaning."
- Internal Developer Portal: "The singular interface to your developer platform. It discovers every aspect of your architecture, organizes it into a knowledge graph, and exposes information as well as actions developers can take."

## Argumento

- "You need both to tame sprawl": a plataforma é um conjunto heterogêneo de ferramentas; o portal unifica o conhecimento espalhado por elas.
- Recomendações: ter os dois; scorecards para definir padrões ("it's only what gets measured that gets managed"); catálogo universal para reduzir drift de metadados; self-serve actions com aprovação como guardrail (golden paths).
- Único número: "over 40 metrics you can use to define a scorecard" — dado do produto, não da indústria.

## Uso na apresentação

- Reforça `portal-is-not-platform` com uma definição curta e citável dos dois termos.
- Discordância com a tese da apresentação: "the **singular** interface" coloca o portal como porta única; aqui o portal é **uma** das interfaces, ao lado de CLI e agentes (`many-clients`, `formae-cli.md`). Bom contraste para dizer em voz alta.
