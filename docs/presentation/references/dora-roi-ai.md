# DORA ROI of AI-assisted Software Development

- Fonte: DORA e Google Cloud (time delta), *The ROI of AI-assisted Software Development*, v. 2026.1, https://dora.dev/ai/roi/report/ (60 pp., licença CC BY-NC-SA 4.0; citações do relatório recuperadas em fevereiro de 2026). Autores: Eva Dong, Andre Ellis Jr., Nathen Harvey, Vivian Hu, Ursula Löbbert-Passing, Eric Maxwell, Aaron Wanjala (p. 51-52). Página abaixo = numeração impressa, que coincide com a do PDF. Lido inteiro em 2026-10-07.
- Calculadora interativa: <https://dora.dev/ai/roi/calculator>. Landing page: <https://dora.dev/ai/roi/report/>.
- **Natureza:** não é survey novo. É um framework de cálculo de ROI apoiado nos achados do DORA 2025 (`dora-ai-report.md`) e numa calculadora com premissas de exemplo. Os números do exemplo (39% de ROI, payback de 8 meses, CFR de 5% para 6%) são **premissas ilustrativas**, não achados — o próprio relatório pede para tratá-los como "high-uncertainty estimate meant to spark a conversation" (p. 23, p. 54).
- **Viés:** coautoria do time de consultoria delta do Google Cloud, que oferece o serviço ao final (p. 27, p. 38, p. 53). Os números de mercado das p. 12 e 36 (78%, 88%, 727%, payback médio de 8 meses) vêm de material comercial do Google Cloud, não de pesquisa DORA — não levar para a tela.

## Resumo

- A tese do relatório: IA é amplificador; o retorno vem do sistema em volta dela (plataforma interna, fluxos, alinhamento de times), não da ferramenta (p. 3, p. 13).
- **Afirma explicitamente o papel do IDP na era agêntica**: provedor de contexto e mitigador de risco para agentes, que também são usuários da plataforma (p. 40). É a fonte mais direta, e não patrocinada por vendor de plataforma, para a tese "IDP para humanos e agentes".
- A adoção segue uma **J-Curve**: queda temporária de produtividade (learning curve, verification tax, pipeline adaptation) antes do ganho (p. 4, p. 8-9).
- O roadmap de investimento começa pela **context layer**: plataforma interna de qualidade e ecossistema de dados saudável, com documentação "machine readable" e um "standardized map" do panorama técnico (p. 44).

## Citações sobre plataforma e agentes

- "In the agentic era, an IDP is no longer just a portal for infrastructure, it is the risk mitigator and the context provider for AI agents." (p. 40, *Treat your Internal Developer Platform (IDP) as a product*)
- "The 2025 research confirms that a quality internal platform is the primary connective tissue for AI value." (p. 40)
- "When AI agents can navigate a well-defined platform, they spend less time hallucinating architectural patterns and more time delivering valuable code." (p. 40)
- "The goal is a platform that treats the developer—or any builder—as the user, minimizing the cognitive load required to move code from an agent's prompt to a production environment. Simultaneously, the platform provides the guardrails for the agents who are also users of the platform." (p. 40)
- "If your organization possesses mature internal developer platforms and streamlined deployment pipelines, AI will rapidly scale your capacity to deliver user value and drive revenue." Com gargalos de teste manual, burocracia ou dados fragmentados, "injecting AI into that system will simply accelerate the accumulation of technical debt and maintenance costs." (p. 7)
- "Without a solid foundation built on quality internal platforms and clear workflows, AI merely generates isolated pockets of productivity. For example, a developer might write code significantly faster using an automated assistant, but that code simply piles up in front of manual security reviews or brittle deployment pipelines." (p. 13)

## Context layer (primeiro investimento)

- "Build the context layer (CapEx). Primary capabilities: quality internal developer platforms and healthy data ecosystems. The first investment must be in the environment in which AI operates. In an agentic world, garbage in, garbage out refers to the context provided to the agent." (p. 44)
- "This involves centralizing architectural standards and ensuring documentation is high fidelity and machine readable. The goal: Minimize friction by ensuring agents have a clear, standardized map of the organization's technical landscape." (p. 44)
- "AI agents are only as effective as the data they can access." Inclui "high-quality documentation, clean APIs, and a healthy data ecosystem"; com conhecimento fragmentado ou desatualizado, "AI generates bloat, duplicated or irrelevant code". Os agentes precisam da "ground truth needed to make accurate decisions within the specific context of your code base." (p. 41)
- Depois da context layer, o investimento vai para as pessoas: "Empower the human in the loop (OpEx)", com treino em "context engineering and verification"; devs "equipped to act as high-level orchestrators" (p. 44).

## Guardrails automatizados

- "This involves shifting from manual checkpoints to automated nonoptional security and quality gates. In an agentic world, these guardrails act as the brakes that allow the engineering engine to go faster safely." (p. 42)
- Contra a verification tax: "technical guardrails, such as nonoptional checkpoints and pre-commit hooks paired with static analysis", "investing heavily in automated testing, leveraging AI to assist with code reviews, and providing better context to the AI to improve initial code quality." (p. 33)
- As cinco chaves da adoção: "trust, platform, data, users, and guardrails" (p. 42).

## J-Curve e verification tax

- "We anticipate that most organizations will encounter a J-Curve: a temporary productivity dip and period of instability associated with early adoption. Think of this dip as the tuition cost of transformation." (p. 4)
- Três fatores da queda (p. 9): **learning curve** (inclusive passar "from users prompting AI to systems built on context, intent, and specification"), **verification tax** (revisar código gerado e o volume maior de código) e **pipeline adaptation** ("testing and change approval must scale to handle the increased volume").
- A profundidade e a duração da curva dependem de maturidade técnica, cultura de aprendizado e "the baseline health of its internal developer platforms" (p. 10).
- Mesmo padrão já observado em "continuous delivery and platform engineering" (p. 8): lideranças cortam o investimento na queda por confundir aprendizado com fracasso.
- "For an individual developer, AI does not necessarily make friction vanish; rather, the friction moves." O esforço economizado em boilerplate vira "a verification tax—the cognitive load required to iterate on prompts and rigorously audit AI-generated code that looks remarkably similar to correct code." (p. 20)
- "If trust is low, the J-Curve deepens as developers second guess every line of code" (p. 40).

## Medir

- "We don't measure AI by the code it writes but by the bottlenecks it clears." (p. 7)
- Indicadores: DORA metrics como "operational early warning system" — lead time para medir o impacto de agentes na velocidade, change failure rate para a eficácia (p. 10); "experiment frequency" (quão frequentemente os times usam agentes para explorar soluções) e deployment frequency como leading metrics; change failure rate e rework como "stability gauge" (p. 45).
- Experiment frequency como opção financeira: IA reduz o "premium" de cada experimento; a organização só "exerce a opção" (manter, escalar, proteger o código) quando o experimento prova valor (p. 46).
- Leading indicators (produtividade, developer experience, user experience) vs. lagging (custo e receita) (p. 22-23).
- Recomendação explícita: **não** usar o ganho para reduzir headcount; reinvestir a capacidade (p. 25, p. 48).

## Números (com a origem)

| Dado | Valor | Página | Origem |
|---|---|---|---|
| Respondentes que percebem aumento de produtividade com IA | mais de 80% | 18 | DORA 2025, p. 30 |
| Maior efeito da IA: individual effectiveness; segundo maior: instabilidade | — | 25 | DORA 2025, p. 38 |
| Custo de inferência de modelos avançados caiu | fator de 280 (nov/2022 a out/2024) | 36 | Stanford AI Index 2025 (secundário) |
| Ganho de produtividade: greenfield simples vs. brownfield complexo | 35-40% vs. 10% ou menos | 36 | Stanford Software Engineering Productivity Research (secundário) |
| Substituir um dev custa | 1,5 a 2x o salário anual | 28 | sem fonte citada |
| Exemplo da calculadora: ROI / payback / CFR | 39% / 0,7 ano / 5% para 6% | 35-36, 57 | premissas ilustrativas |

- Consequência que o relatório tira do custo de inferência: "the true financial burden of adoption has shifted to governance cost: managing the verification tax, adjusting workflows, and upskilling talent." (p. 36)

## Não verificado

- Os números de Stanford (280x, 35-40% vs. 10%) não foram conferidos na fonte original.
- Os números de mercado do Google Cloud (78% dos executivos com ROI, 88% dos early adopters agênticos com retorno, 727% em três anos, payback médio de 8 meses) são material comercial — não usar.
- "5 strategic priorities" (p. 13) vêm de "an internal research study conducted by Google in 2025", não publicado.

## Uso na apresentação

- **Slide-tese do ato final (`aep-evolution` ou equivalente):** a citação da p. 40 — "risk mitigator and the context provider for AI agents" — fecha o arco "IDP para humanos e agentes" com fonte neutra em relação ao Kratix/Syntasso.
- **`catalog-as-context`:** "clear, standardized map of the organization's technical landscape" (p. 44) é a descrição do catálogo; combinar com o `mcp-actions-backend` do Backstage (`mcp-platform-interface.md`).
- **`platform-readiness` / `rebuild-platform`:** "code simply piles up in front of manual security reviews or brittle deployment pipelines" (p. 13) dá a imagem concreta do gargalo; complementa o DORA 2025 (p. 71).
- **`ci-bottleneck` e paths determinísticos:** "guardrails act as the brakes that allow the engineering engine to go faster safely" (p. 42).
- **`token-finops`:** custo migrou de inferência para governança (p. 36); casa com "cost per accepted output" do State of AI.
- **`mvp1` / `where-we-are`:** a J-Curve explica para o público executivo por que o MVP 1 mede custo e não promete ganho imediato; experiment frequency liga com `Environment` sob demanda e sandbox por requisição.
- Ressalvas nas notas: coautoria da consultoria do Google Cloud; exemplo da calculadora é premissa, não dado.
