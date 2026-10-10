# Port practical guide to internal developer portals

- Fonte: "The practical guide to internal developer portals", publicado pela Port (https://www.port.io/guide; PDF em https://info.port.io/hubfs/The%20Practical%20Guide%20to%20Internal%20Developer%20Portals.pdf), criado em março de 2024. 40 páginas; a numeração impressa coincide com a do PDF (capa = p. 1). O guia não declara autores individuais.
- **Material de vendor.** A Port é um internal developer portal comercial e concorrente direto do Backstage; o guia diz que "isn't a plug for our technology" (p. 4), mas termina com a promoção do produto (p. 40) e cita Port como exemplo ao longo do texto. Toda afirmação que favorece um portal comercial (un-opinionated, blueprints, real-time sync, open-source extensibility) é opinião do vendor, não evidência independente. O guia não traz pesquisa própria: o único dado numérico externo é o da Puppet Labs (p. 3).

## Resumo

- Plataforma (IDP) e portal são coisas distintas: a plataforma é o conjunto de ferramentas para build, deploy e operação; o portal é a interface com as abstrações certas para o desenvolvedor. A plataforma é "necessary but not sufficient" (pp. 6-7).
- O portal se apoia em quatro pilares: self-service actions, software catalog, scorecards e automations, todos definidos sobre blueprints (metadata schemas) e relations (pp. 7-10, 14-15).
- O data model deve ser definido pela organização (un-opinionated), guiado por personas e pelas perguntas que se quer responder, e deve incluir dados de runtime ("running service"), não só metadata estática (pp. 11, 15-18, 20).
- Boas práticas de design: extensible, loosely coupled, API-first, portal-as-code e customizable com RBAC por persona; self-service deve ficar desacoplado da infraestrutura e do GitOps subjacentes (pp. 11-13, 21).
- Reporting e executive views são tratados como valor subestimado, e a adoção é o risco central: integrar ao workflow do desenvolvedor, começar com MVP, adotar product mindset e rollout incremental (pp. 31-34, 38-40).

## Argumento por capítulo

- Introdução, pp. 3-4 — a era da plataforma: platform engineering substitui o DevOps tradicional, com desenvolvedores como "customers"; complexidade do Kubernetes, migração para SaaS e fragmentação de ferramentas motivam golden paths e guardrails; o portal é apresentado como nova categoria de produto.
- Cap. 1, pp. 5-13 — Overview: diferença entre IDP e portal, os quatro pilares e seis considerações de design (un-opinionated, extensible e open, loosely coupled, API-first, portal-as-code, customizable).
- Cap. 2, pp. 14-16 — Blueprints: schema de metadata de cada tipo de entidade, ligadas por relations (grafo); definem catálogo, actions e scorecards; ajustáveis no tempo; incluem contexto de runtime.
- Cap. 3, pp. 17-20 — Software catalog: não é inventário estático; data model guiado por personas; modelos base (Classic/SDLC e C4) e extensões (K8s, API catalog, cloud resources, CI/CD, packages, vulnerabilities, incidents, alerts, tests, feature flags, misconfigurations, FinOps); catálogo stateful e em tempo real.
- Cap. 4, pp. 21-23 — Developer self-service actions: autonomia com guardrails e golden paths; actions refletidas no catálogo; exemplos por domínio; actions assíncronas, manual approval e run logs.
- Cap. 5, pp. 24-28 — Scorecards: medem saúde e maturidade de cada entidade do catálogo; tipos (readiness, maturity, DORA, migration, health, code quality, cloud cost, security); initiatives agrupam scorecards; usos como revisão periódica e como alerta/gate de CI/CD; processo de quatro passos.
- Cap. 6, pp. 29-30 — Automations: trigger + action sobre a API do portal (escalonar incidente, remediar segurança, limpar recursos, bloquear deploy).
- Cap. 7, pp. 31-34 — Reporting e executive views: relatórios por persona (developer, product manager, executivo, CIO); tipos usage, health, productivity e business impact; scorecards e initiatives como insumo.
- Cap. 8, pp. 35-37 — Extensibility: valor cresce com os dados; requisitos de real-time sync, bi-directional sync, reconciliation, secure by design e protocolos flexíveis; defesa de framework de integração open source.
- Cap. 9, pp. 38-40 — Adoption strategy: armadilhas (não integrar ao workflow, excesso de features, falta de sponsorship), product mindset, Team Topologies para mapear equipes, rollout focado e iterativo; conclusão e apresentação da Port (p. 40).

## Números

O guia tem pouquíssimos números. Valores marcados como "exemplo" são parâmetros ilustrativos do texto, não dados de pesquisa.

| Dado | Valor | Página | Fonte original citada pelo guia | Uso sugerido |
|---|---|---|---|---|
| Organizações que adotaram platform engineering ou planejam adotar no próximo ano | 51% | 3 | Puppet Labs (sem título, ano nem link do relatório) | Adoção de platform engineering; usar com cautela, citar a Puppet Labs e não a Port, e conferir o relatório original (State of DevOps) antes de colocar em slide |
| Ciclo de scorecard: exemplo de check "code coverage > 70%" e amarelo abaixo de 80% | 70% / 80% | 27 (diagrama) | sem fonte (exemplo ilustrativo) | Não usar como dado; no máximo ilustrar a mecânica de thresholds |
| Exemplo de alerta de scorecard: uptime abaixo de 99% | 99% | 24 | sem fonte (exemplo ilustrativo) | Não usar como dado |
| Exemplo de self-service: ambiente de desenvolvimento por 5 dias; extend TTL por 3 dias | 5 dias / 3 dias | 9, 22 | sem fonte (exemplo ilustrativo) | Ilustrar ambiente efêmero com TTL |
| Quantidade de pilares do portal / considerações de design / tipos de time (Team Topologies) / passos de scorecard | 4 / 6 / 4 / 4 | 8, 11, 39, 27 | Team Topologies (Skelton e Pais, 2019) para os quatro tipos de time (p. 39); demais sem fonte (framework do guia) | Estrutura do argumento, não evidência |

O guia não traz métricas de adoção, ROI, tempo economizado nem comparação com Backstage. Não há número de adoção para contrapor ao material de adoção do Backstage já em `backstage-catalog.md`/referências anteriores.

## Citações

- "An internal developer platform is necessary but not sufficient. It centralizes everything DevOps – but still requires an interface that provides the right abstractions for developers and promotes golden paths." (p. 6)
- "Internal developer portals are the answer. They act as a user-friendly interface to the platform – abstracting the complexity of the software development environment by providing a single user interface that's built for the questions and needs of different dev teams." (p. 7)
- "It can't be the other way around. In other words, the portal can't dictate the organization's use cases and priorities." (p. 7)
- "A blueprint is a metadata schema definition – each blueprint defines the assets that the portal can manage and track" (p. 7)
- "when you order a ticket from an airline you don't want to choose the pilot and other flight staff. The same applies for developer self-service actions: the form should only include what developers care about" (p. 9, atribuído a Kostis Kapelonis)
- "An internal developer portal isn't a static list of microservices; it's a dynamic graph of all your entities in context." (p. 18)
- "Your code is not your app." (pp. 16, 20)
- "Self-service actions should be loosely coupled (deliberately segregated) from the underlying infrastructure of the platform." (p. 21, texto extraído com ruído; a ideia está também na p. 12)
- "it's considered best practice for the portal to remain loosely coupled from underlying GitOps platforms." (p. 21)
- "An API-first portal will have a generic interface to model the software catalog, ingest data, invoke actions, query scorecards and more – providing an optimized experience for both humans and machines." (p. 12)
- "Reporting is almost always treated as an afterthought in conversations about internal developer portals." (p. 31)
- "even the most advanced portal will fail without a sound adoption strategy." (p. 38)
- "Developers reject the portal if it doesn't integrate into their workflows." (p. 38)
- "Executive sponsorship is necessary – but far from sufficient – to ensure adoption." (p. 38)
- "Low usage may indicate poor marketing rather than a bad product." (p. 32)
- "low utilization of a new tool may indicate UX issues rather than inherent low value." (p. 39)
- "In their rush to implement scorecards, too many teams rush through the critical phase of discussing quality and standards with teams." (p. 27)
- "An effective internal developer portal requires more than just technical buildout – it demands cultivating users." (p. 40)

## Conceitos e frameworks

- **Internal developer platform vs. portal** — plataforma = hub de ferramentas (CLI, CI/CD, provisioning); portal = interface com abstrações para o desenvolvedor, que aciona ações em ferramentas como o Jenkins em vez de usá-las direto (pp. 6-7).
- **Golden path** — "single supported approach" para tarefas como criar um backend service ou data pipeline (pp. 3, 6).
- **Blueprint** — schema de metadata de um tipo de entidade (microservices, environments, packages, clusters, databases, dados de terceiros); aceita qualquer número de propriedades, alteráveis; também é onde se definem self-service actions e scorecards (pp. 7-8, 14-15).
- **Relation** — conexão entre blueprints (um-para-um, um-para-muitos); faz o catálogo ser um grafo (pp. 7, 14).
- **Software catalog** — repositório central de metadata de software e recursos subjacentes, atualizado continuamente, "single pane of glass", fonte de verdade que pipelines podem consultar (TTL de ambiente, ownership, feature flags) (pp. 9, 17); sincroniza com o identity provider para refletir ownership (p. 17).
- **Data models base** — Classic/SDLC (Service, Environment, Running Service) e C4 (adaptação do modelo C4 do Backstage: Context, Containers, Components, Code) (p. 18). Extensões para DevOps (K8s, API catalog, cloud resources, CI/CD) e para todos os devs (packages, vulnerabilities, incidents, alerts, tests, feature flags, misconfigurations, FinOps) (pp. 19-20).
- **Running service / stateful catalog** — entidade que representa a versão viva de um serviço em um ambiente; o guia insiste que o catálogo deve incluir dados de runtime e sincronizar em tempo real com CI/CD (pp. 16, 18, 20).
- **Self-service actions** — formulários curados pelo platform team; cobrem provisioning, day-2 operations, ambientes efêmeros com TTL, aprovação manual; toda action cria, altera ou remove entidades do catálogo; run logs dão visão curada em vez do log completo do pipeline (pp. 9, 21-23). Exemplos por domínio: SDLC, developer environments, cloud resources, SRE, Data & ML (p. 22).
- **Scorecards** — benchmarks por entidade do catálogo; tipos: operational readiness, service maturity, operational maturity, DORA, migrations, health, code quality, cloud cost, security (pp. 10, 24-25). Três razões de uso: alinhamento organizacional, alerta e priorização, melhoria de qualidade (pp. 24-25).
- **Initiatives** — grupos de scorecards ligados a uma área estratégica (ex.: "Improve Reliability"); alinham workflows a KPIs de negócio (pp. 25-26).
- **Uso de scorecards** — revisão periódica por gestores e como alerta/gatilho de automação, incluindo CI/CD que interrompe deploy se o tier do scorecard estiver baixo (pp. 26-27).
- **Scorecard em 4 passos** — discutir qualidade e padrões com as equipes, definir checks, definir thresholds (vermelho/amarelo/verde e alertas), adotar e avaliar (p. 27, diagrama; o texto de extração não traz esses passos, foram lidos na imagem).
- **Automations** — par trigger + action; triggers: entidade casa condição, formulário enviado, entidade criada ou atualizada, horário agendado, scorecard degrada; actions: e-mail, Slack, weekly digest, job, chamada de API, bloquear deploy (pp. 29-30). Habilitadas pela API do portal (p. 29).
- **Seis considerações de design** — un-opinionated vs. opinionated, extensible e open, loosely coupled, API-first, portal-as-code (configurar o portal por código, p. ex. Terraform), customizable com RBAC fino por persona (pp. 11-13).
- **RBAC** — citado como requisito de customização por persona e como reforço do golden path na UI (pp. 13, 21).
- **Reporting** — relatórios por persona (developers, product managers, executivos, CIOs) e por tipo (usage, health, productivity/DORA, business impact); customização de definições de métrica, visualização, frequência e documentação (pp. 31-33).
- **Extensibility** — real-time continuous sync, bi-directional sync, reconciliation com a fonte como ground truth, secure by design (sem compartilhar credenciais nem whitelist de IP), protocolos flexíveis (webhooks, APIs, message queues) (p. 36); defesa de integration framework open source (pp. 36-37).
- **Adoção** — armadilhas: não integrar ao workflow, começar com features demais, falta de executive sponsorship (p. 38); rollout em dois passos: mapear a estrutura de equipes via Team Topologies (stream-aligned, enabling, complicated subsystem, platform) e adaptar o rollout (entrevistas e surveys, caso de uso focado, monitorar uso, feedback, champions, expansão por demanda) (p. 39). Cita "platform-as-product" como a abordagem de escolha do portal (p. 5).

## Relevância por plane

- **Developer Control Plane** — é o plane central do guia: portal, self-service actions, catálogo e scorecards são todos interface com o desenvolvedor (pp. 6-10). O guia trata o portal como a interface única ("single user interface", p. 7), embora também diga que o portal API-first serve "humans and machines" (p. 12) e que pipelines consultam o catálogo (p. 9).
- **Integration & Delivery Plane** — self-service actions disparam CI/CD e GitOps (pp. 6, 21); scorecards bloqueiam deploy (p. 27); CI/CD alimenta o catálogo em tempo real (p. 20); o guia recomenda manter o portal desacoplado do GitOps (p. 21), o que combina com o papel de orquestração fora do portal.
- **Resource Plane** — provisionamento de recursos de nuvem por self-service com guardrails e extensão de data model com cloud resources e K8s (pp. 9, 19, 22); limpeza automática por TTL (pp. 10, 29).
- **Observability Plane** — alerts, incident management e FinOps como extensões do catálogo (pp. 19-20, 35); reporting de usage, health, DORA e business impact (pp. 32-33).
- **Security Plane** — scorecards de segurança, vulnerabilities e misconfigurations no catálogo (pp. 19-20, 25); RBAC (pp. 13, 21); secure by design nas integrações (p. 36); auto-remediação (p. 29). O guia não trata identidade de agentes nem IA.

## Relação com a apresentação

- **Catálogo como conceito humano, não só ferramenta.** Reforça: o guia diz que o data model deve nascer das perguntas que a organização quer responder e das personas (pp. 15, 17), e que o portal "can't dictate" os casos de uso (p. 7). Contradiz em parte a ideia de catálogo como arquivo estático versionado: o guia exige catálogo stateful, atualizado em tempo real, com "running service" (pp. 16, 20). O `backstage-catalog.md` já registra que o catálogo Backstage não guarda versões, e esse é exatamente o ponto em que o guia posiciona o modelo de blueprints como superior (opinião de vendor).
- **Portal como um cliente entre CLI e agentes.** O guia contradiz parcialmente essa tese: trata o portal como a camada de abstração e fonte de verdade para o desenvolvedor, e a plataforma "sem portal" como insuficiente (p. 6). Porém admite que o portal é API-first, atende "humans and machines" e que a API serve para scripts, CI/CD e automações (pp. 12-13, 29), o que sustenta a ideia de que o catálogo e as actions podem ser consumidos por outros clientes. O guia não menciona agentes de IA nem CLI como cliente de primeira classe da plataforma.
- **"Platform façade" do relatório O'Reilly (`platform-as-a-product.md`).** O relatório O'Reilly/Syntasso critica "portal + pipeline" sem orquestração como fachada. O guia da Port é um exemplo do que o relatório critica: o portal é o centro, os pipelines (Jenkins, GitOps, CI/CD) ficam atrás e o próprio guia recomenda que o portal permaneça "loosely coupled" dos sistemas subjacentes (pp. 6, 12, 21). Não há conceito de orquestração, estado desejado persistente nem reconciliação de recursos (a "reconciliation" do guia, p. 36, é de sincronização de dados do catálogo com a fonte, não de controle de recursos). Útil como contraponto: mostra o argumento do portal-centric que o relatório O'Reilly e a apresentação (orquestrador atrás do portal: Kratix em avaliação, Crossplane no IaC) rebatem.
- **Métricas de adoção.** O guia trata adoção como risco principal (p. 38), recomenda monitorar uso para detectar obstáculos (p. 39) e sugere relatórios de adoção da plataforma (p. 31), mas não traz nenhum número de adoção. O único número é o 51% da Puppet Labs (p. 3). Para métricas de adoção do Backstage, a base continua sendo o material já registrado em referências anteriores, não este guia.
- **Scorecards vs. scorecard do Platform as a Product.** O O'Reilly usa um scorecard da plataforma (quatro pilares, uma métrica-chave por pilar, p. 4-5 do relatório) para medir a plataforma como produto. O guia da Port usa scorecards para medir cada serviço (entidade do catálogo): readiness, maturity, DORA, segurança, custo (pp. 24-25). São escopos diferentes: o da Port avalia os serviços dos times; o do O'Reilly avalia a plataforma. Initiatives (pp. 25-26) se aproximam mais de um scorecard de plataforma, mas continuam agrupando scorecards de serviço. Os relatórios de usage e adoção do guia (pp. 31-33) é que tocam a medição da plataforma em si.
- **Port (blueprints) vs. Backstage (entity model).** Port é portal-centric e un-opinionated: cada organização define seus blueprints e relations como schema livre, e o catálogo é um grafo dinâmico (pp. 11, 14-15, 18). O Backstage tem um modelo de entidades opinionado (Component, API, Resource, System, Domain, User/Group, ver `backstage-catalog.md`) com `owner` em todas. O guia admite o contraste ao descrever o C4 como "adaptação do Backstage C4 Model" (p. 18) e cita um guia de migração Backstage para Port (p. 18, só título, não lido), mas não discute as limitações do Backstage além do rótulo "opinionated" (p. 11), que é argumento comercial. Fazer a comparação com cuidado: "opinionated é rígido" é opinião do vendor; também se pode ler o modelo fixo do Backstage como vantagem de consistência entre organizações.
- **Pontos de uso na apresentação.** (1) Definição IDP vs. portal (pp. 6-7), útil para separar "plataforma" de "interface" nos slides dos planes. (2) Os quatro pilares como vocabulário de portal (p. 8). (3) Dados de runtime ("your code is not your app", pp. 16, 20) como argumento para estado vivo no catálogo. (4) Pitfalls de adoção (p. 38), úteis como alerta, citando sempre como visão de vendor.

## Anomalias de leitura

- Todas as 40 páginas têm texto extraível. A p. 27 tinha o diagrama dos 4 passos de scorecard como imagem; foi lida renderizada.
- Alguns trechos têm ruído de extração (p. 21, p. 36 "Rapid innovation"); as citações acima foram reconstruídas com cuidado.
- O guia remete a vários artigos do blog da Port ("Further Reading") que não foram lidos: não tratar o conteúdo deles como parte desta referência.
