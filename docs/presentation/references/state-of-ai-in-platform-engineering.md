# State of AI in Platform Engineering Vol. 2

- Fonte: *State of AI in Platform Engineering, Volume 2* (https://weaveintelligence.io/research/state-of-ai-in-platform-engineering-2026) (Weave Intelligence, 2026; autores Sam Barlien, Luca Galante, Florian Lipp; parceiros Thoughtworks, Vultr, Syntasso, env zero, Microsoft). Metodologia (p. 55): 350 profissionais globais, coleta de abril a agosto de 2026, 24 questões; perfil: contribuidores individuais 31%, team leads 27%, heads of function 19%, VP/director/C-level 23%. Os níveis de maturidade e os ganhos são autorrelatados (p. 18, p. 21). Numeração de página abaixo = numeração impressa do PDF.

## Resumo

- O dado central do relatório: 38% das organizações entregam pelo menos o dobro desde a adoção de IA, mas só 8% descrevem o retorno como transformador. Todo o relatório explora essa lacuna (p. 8, p. 54).
- O gargalo não é o modelo, é a plataforma: "platform readiness" lidera os obstáculos para escalar IA (27%), "model capability" fica em quarto (11%) (p. 24).
- A maturidade paga em degrau, não em gradiente: colocar agentes sem reconstruir a plataforma adiciona 6 pontos percentuais de throughput; reconstruir a plataforma adiciona 24 (p. 21).
- A geração de código industrializou, a absorção não: 35% ainda validam mudanças geradas por IA só por leitura humana e apenas 17% rodam validation loops automatizados (p. 26).
- A governança é o ponto mais frágil: um quarto roda agentes com credenciais humanas emprestadas, 12% com service account compartilhada e 18% não sabem como a identidade de agentes é gerida (p. 38). O Agentic Engineering Platform (AEP) é apresentado como a evolução do IDP, não a sua substituição (p. 28-30).

## Números

| Dado | Valor | Página | Uso sugerido na apresentação (ato/tema) |
|---|---|---|---|
| Organizações que entregam pelo menos 2x mais desde a IA (Figure 7, "Change in engineering throughput since adopting AI": 29% com 2x-3x + 9% com 5x ou mais) | 38% | 8, 20, 23 | Por que plataformas: abertura, par com a linha seguinte |
| Organizações que descrevem o retorno de IA como transformador (Figure 9, "Current ROI of AI across the SDLC"; 29% pre-value, 14% negativo) | 8% | 8, 22 | Por que plataformas: a lacuna throughput vs. ROI |
| Plataformistas que usavam IA todo dia (Vol. 1) | 89% | 12 | Adoção de IA em platform engineering |
| Organizações com pouco ou nenhum retorno de IA (Vol. 1) | 95% | 12 | Contexto histórico do "AI implementation plateau" |
| Organizações no Level 1 ou abaixo há 12 meses | mais de 95% | 12, 19 | Evolução de maturidade em um ano |
| Plataforma entrega conectividade LLM central | 45% | 13 | Agentes/IA: o time de plataforma assume IA |
| Plataforma entrega interfaces de retrieval/chat | 35% | 13 | Agentes/IA |
| Plataforma entrega agent runtimes | 27% | 13 | Agentes/IA: agent runtime como serviço de plataforma |
| Plataforma entrega inference workloads | 27% | 13 | Agentes/IA |
| Organizações sem mandato de IA | 15% | 13 | Adoção de IA |
| IA como iniciativa de produtividade company-wide / estratégica C-level | 36% / 33% | 14 | Adoção: mandato vem de cima |
| Adoção grassroots por engenheiros individuais / sem atividade | 6% / 3% | 14 | Adoção de IA |
| Casos de uso: code generation / documentação | 84% / 79% | 15 | Adoção de IA no SDLC |
| Casos de uso: análise de erros e logs / geração de IaC | 66% / 65% | 15 | Resource Plane e Observability: IaC gerado por IA |
| Consumo de LLM: API direta de provider / hosting agregado / self-host open source / provider soberano | 52% / 26% / 11% / 3% | 16 | Security Plane: governança de acesso a modelos |
| Temem exposição de dados via APIs públicas de IA | 64% | 16, 40 | Security Plane |
| Maturidade: Level 1 / Level 2 / Level 3 / Level 4 / não sabe | 41% / 31% / 14% / 4% / 9% | 19 | Agentes operando plataformas: onde a indústria está |
| Organizações acima do Level 2 | 18% | 19 | Agentes/IA: poucos passaram do Level 2 |
| Level 4: organizações com menos de 100 engenheiros | 13 de 14 | 20 | Governança: autonomia ainda é conquista de time pequeno |
| Throughput: ganho marginal (<20%) / sem mudança mensurável / 2x a 3x / perto de 5x ou mais | 39% / 23% / 29% / 9% | 20 | Medição de sucesso: mesma tecnologia, resultados díspares |
| Pelo menos dobrou throughput por nível (Level 1 / 2 / 3 / 4; Figure 8, "Share reporting at least doubled throughput (2x to 3x, or 5x and above), by agentic maturity level") | 30% / 36% / 60% / 79% | 21 | Medição: maturidade paga em degrau (n = 143 / 110 / 50 / 14) |
| Ganho de agentes sem reconstruir plataforma (Level 1 para 2) vs. reconstruindo (Level 2 para 3) | 6 pontos percentuais vs. 24 | 21 | Por que plataformas: o argumento principal |
| ROI com impacto transformador por nível (Level 1 / 2 / Level 3 ou 4) | 2% / 9% / mais de 20% | 23 | Medição de sucesso |
| ROI pré-valor (só experimentação) / ROI negativo | 29% / 14% | 22 | Medição: custo de licenças, tokens e revisão |
| Obstáculos para escalar IA: platform readiness / custo de tokens e infra / review bandwidth / model capability | 27% / 23% / 16% / 11% | 7, 24 | Por que plataformas: "ninguém espera um modelo melhor" |
| Código gerado por IA melhorou estabilidade / mais ruído e falhas de CI / sem impacto / não sabe | 39% / 12% / 29% / 20% | 25 | Integration & Delivery: qualidade não é o problema |
| Validação de mudanças de agentes: só leitura humana / validation loops automatizados / não sabe | 35% / 17% / 13% | 26 | Integration & Delivery: gargalo de absorção |
| Review bandwidth como maior gargalo: Level 1 para Level 2 | 12% para 23% | 33 | Integration & Delivery: agentes em paralelo batem no muro de review |
| Não rastreiam gasto de tokens / não sabem se alguém rastreia | 13% / 14% | 35 | Observability: FinOps de tokens |
| Quem rastreia: billing centralizado / rate limits ou quotas / custo distribuído por time | 35% / 22% / 17% | 35 | Observability e governança: FinOps |
| Level 1 e 2 que não rastreiam gasto de tokens | 15% | 36 | Observability: custo como pré-condição do Level 3 |
| Postura de segurança: governa por políticas e controles específicos de IA / bloqueia ou restringe | 37% / 13% | 37 | Security Plane: guardrails em vez de veto |
| Agentes com identidade própria com escopo / identidade gerida dinamicamente por política | menos de 1 em 3 / 19% | 38 | Security Plane: identidade de agente |
| Agentes com credenciais humanas / service account compartilhada / sem saber (Figure 16, "How AI identities are managed in the platform"; menos de 1 em 3 com identidade própria com escopo, 19% dinâmica por política) | 25% / 12% / 18% | 38 | Security Plane: blast radius |
| Usam IA para gerar infraestrutura como código | 65% | 39 | Resource Plane e Security: controles param na fronteira do código |
| Agentes burlando controles existentes como ameaça relevante | 43% | 39 | Security Plane |
| Riscos de IA: hallucinations em produção / uso não gerenciado de tools / data residency e auditabilidade / prompt injection | 52% / 47% / 43% (cada) / 37% | 40 | Security Plane |
| Shadow AI: mínimo / significativo / sem visibilidade | 47% / 27% / 8% | 40 | Security e Observability: "observability has to precede restriction" |
| Clientes da plataforma: times de software / data science e ML / business users / externos / agentes | 79% / 49% / 48% / 20% / 29% | 43 | Developer Control Plane: agentes como clientes da plataforma |
| Expectativa do papel do platform engineer: governança e guardrails / plataformas para agentes / sem mudança / automatizado | 43% / 36% / 11% / 9% | 44 | Developer Control Plane e governança |
| Times de plataforma e dados: silos separados / convergidos / convergindo | 28% / 6% / 10% | 45 | Portal/catálogo: expansão do mandato |
| Prioridade de investimento em 12 meses: automação do SDLC / agentic coding / remediação de incidentes e segurança e compliance (cada) / DevEx e copilots | 31% / 23% / 16% / 13% | 53 | Agentes operando plataformas |
| Previsão do relatório: organizações em Level 3 ou acima no próximo ano | mais de 30% (hoje 18%) | 53 | Roadmap: onde a indústria vai |

## Citações

- "The Agentic Engineering Platform is the evolution of the IDP, not the replacement of it." (Kaspar von Grünberg, p. 28)
- "an agent without specially designed controls and validation checkpoints does not fail gracefully; instead, it generates chaos at machine speed." (p. 28)
- "Nobody is waiting for a better model." (p. 7; reforçado em p. 54)
- "Generation industrialized. Absorption did not." (p. 7)
- "An agent that cannot be identified cannot be audited, scoped, or switched off without switching off a person" (p. 7)
- "tighter governance actually raises the autonomy ceiling instead of lowering it." (p. 41)
- "Organizations that throw agents at a Level 1 substrate will find their agents moving faster than their guardrails." (p. 30)
- "AI has made code cheap and judgment expensive." (Irina Gontcharova, Microsoft, p. 26)
- "It's because they have the platform around the model." (Rickey Zachary, Thoughtworks, p. 24)
- "the discipline exists because recurring work in software development, when done by humans, was being relentlessly ad hoc ... Define the path once, govern it, and let everyone run it." (p. 16, trecho resumido: "Define the path once, govern it, and let everyone run it")

## Conceitos e frameworks

- Quatro níveis de desenvolvimento agêntico (p. 18): Level 0 Human is the loop (sem agentes; baseline do IDP), Level 1 Human in the loop (IA sugere, humano executa), Level 2 Human on the loop (agentes geram PRs em paralelo), Level 3 Humans as orchestrators (agentes trabalham continuamente a partir de sinais observados, review por exceção), Level 4 Fully autonomous (sistemas de agentes dentro de guardrails desenhados por humanos).
- Agentic Engineering Platform (AEP) (p. 27-30, glossário p. 56): o que o IDP vira quando agentes são usuários dele; evolução do IDP, não substituição.
- Três camadas do AEP (p. 29): tooling layer (as cinco planes: developer control, integration and delivery, resource, security, observability; marcada como o IDP), paths layer (rotas repetíveis, governadas e executáveis por máquina) e agent infrastructure layer (identidade, contexto, capability, execução, avaliação, segurança, observabilidade, tudo as code).
- Tipos de path (p. 29): Deterministic (pipeline, mesma saída para a mesma entrada), Probabilistic (agente, "Evals become the test suite"), Hybrid (geração probabilística com gates determinísticos em loop). Recomendação: nomear o tipo de cada path e exigir gates determinísticos em efeitos irreversíveis.
- Os quatro pré-requisitos do Level 3 (p. 10, p. 50): dispatch path, validation loop, scoped identity, sandboxed environments, que só pagam em conjunto.
- Validation gate vs. validation loop (p. 30, glossário p. 58): gate é checkpoint binário; loop devolve a falha ao agente com o motivo até os checks determinísticos passarem ("first-pass failure is convergence, not defect").
- Seis vetores de retorno (p. 34): delivery velocity, outcome predictability, operational resiliency, maintenance overhead, organizational learning, structural incentives.
- Métrica "cost per accepted output" em vez de custo por token (p. 36, p. 51); quatro funções do FinOps de tokens: atribuir cada chamada, vigiar velocidade de gasto, impor limites rígidos na plataforma, produzir trilha de auditoria (p. 36).
- Seis perguntas de cobertura (p. 50): existe path governado e executável por máquina em Plan, Code, Review, Test, Deploy, Monitor? 0-2 sim = substrato é o trabalho; 3-4 = "expensive middle"; 5-6 = restrição já migrou para custo e arquitetura.
- Cinco recomendações (p. 50-51): construir os quatro pré-requisitos do Level 3 juntos; fechar o validation loop antes de adicionar capacidade de agentes; corrigir atribuição (sem credenciais humanas emprestadas); gate por consequência, não por categoria (dano possível e velocidade de detecção); medir valor, não output.
- Padrões de governança dos líderes (p. 41): política, identidade e rede herdadas do workspace; separação de privilégios humano/agente (least privilege, writes só via pull request); workspaces efêmeros; falha controlada e registrada em vez de incidente silencioso.
- AI implementation plateau (p. 12, glossário p. 56) e "Platform as a product, golden paths, standardization" como diferenciais dos que passaram o platô (p. 12).
- Thinking in Platforms e modelo "Paths to Outcome" (p. 47); IDP definido no glossário como plataforma que padroniza paths, habilita self-service e reduz cognitive load (p. 57).

## Relevância por plane

- Developer Control Plane: agentes já são clientes da plataforma em 29% das organizações e 43% esperam o papel migrar para governança e guardrails (linhas "Clientes da plataforma" e "Expectativa do papel"); dispatch path como primeiro path novo do Level 2 (p. 56); maturidade em degrau (linhas de throughput por nível e 6 vs. 24 p.p.).
- Integration & Delivery Plane: gargalo de absorção (35% só leitura humana vs. 17% loops; review bandwidth de 12% para 23% do Level 1 para o 2); validation loop como motor (p. 30); código de IA não degrada estabilidade (39% melhora, 12% piora); cobertura Plan/Code/Review/Test/Deploy/Monitor (p. 50).
- Resource Plane: 65% usam IA para gerar IaC e 66% para análise de erros e logs (p. 15, p. 39); controles atuais inspecionam código, não o efeito no ambiente provisionado; policy-as-code e sandboxed execution ainda minoritários (p. 39); gate por consequência (p. 51).
- Observability Plane: FinOps de tokens (13% não rastreiam, 14% não sabem, 15% nos Levels 1 e 2; atribuição por time, path e modelo; "cost per accepted output"); shadow AI (47% mínimo, 27% significativo, 8% sem visibilidade; "observability has to precede restriction", p. 41); 66% usam IA em análise de logs.
- Security Plane: identidade de agente (25% credenciais humanas, 12% service account, 18% não sabem, 19% dinâmica por política); 37% governam por política vs. 13% bloqueiam; riscos (64% exposição de dados, 52% hallucinations, 47% uso não gerenciado, 43% bypass de controles, 37% prompt injection); padrões dos líderes (workspace-level, least privilege, workspaces efêmeros, p. 41).
- Portal/catálogo: o relatório não trata portais de forma direta (nenhuma menção a Backstage ou catálogo nas páginas lidas); usar apenas o conceito de path como "repeatable route from intent to usable output" (p. 29), golden paths como diferencial (p. 12) e a expansão de clientes (business users 48%, data/ML 49%, p. 43) para justificar um portal único para humanos e agentes. Kratix aparece só como produto do parceiro Syntasso (p. 5-6), não como achado da pesquisa.
- Agentes/IA: maturidade (41/31/14/4/9%), throughput por nível (30/36/60/79%), 6 vs. 24 p.p., quatro pré-requisitos do Level 3, tipos de path, tooling vs. agent infrastructure, previsão de mais de 30% em Level 3 ou acima, prioridades de investimento (31% automação do SDLC); por que "platform readiness" (27%) vence "model capability" (11%).

- Definição dos níveis (Figure 5, p. 18): Level 0 "Human is the loop" (sem agentes; baseline do IDP); Level 1 "Human in the loop" (AI suggests, humans execute); Level 2 "Human on the loop" (agentes geram PRs em paralelo; humanos disparam e verificam comportamento); Level 3 "Humans as orchestrators" (agentes trabalham continuamente a partir de sinais observados; review por exceção); Level 4 "Fully autonomous" (sistemas de agentes iniciam e concluem trabalho dentro de guardrails desenhados por humanos).
