# Platform as a Product (O'Reilly / Syntasso)

- Fonte: *Platform as a Product* (https://www.syntasso.io/platform-as-a-product-oreilly-report) — Abby Bangser, Daniel Bryant, Colin Humphreys e Cat Morris, O'Reilly Media, primeira edição, outubro de 2025 (copyright 2026). Os quatro autores são da Syntasso (empresa por trás do Kratix): o relatório é patrocinado por vendor e defende orquestração, mas não menciona Kratix nem Promise no texto, só na bio de Abby Bangser (core contributor do Kratix).
- Páginas citadas abaixo são as impressas no livro (capítulo 1 começa na p. 1); o PDF tem um offset de cerca de 6 páginas de front matter.

## Resumo

- Plataforma deve ser tratada como produto, não como projeto de infraestrutura: tem usuários, proposta de valor, feedback loop, iteração e foco em adoção (pp. 3-4, 9-11).
- Portal + pipeline/workflow engine formam uma "platform façade": parecem plataforma, mas sem orquestração (estado persistente, política, ownership, ciclo de vida) a plataforma decai (pp. 15-18).
- Orquestração é a camada de controle persistente que coordena capacidades, mantém estado, aplica política e permite evolução segura; portais são onde o usuário interage, pipelines são ferramentas de execução (pp. 16, 19).
- Sucesso se mede em quatro pilares (speed, safety, efficiency, scalability) com um scorecard e uma métrica-chave por pilar, evitando vanity metrics (pp. 4-5, 31-36).
- A plataforma escala por contribuição (platform democracy / multiplayer mode), fleet management e versionamento, e o futuro inclui IA dentro da plataforma, sempre sobre contratos, política e auditoria (pp. 21-29, 37-40).

## Argumento por capítulo

- Cap. 1, pp. 1-7 — The Platform Imperative: complexidade cloud native gera a necessidade de IDP; DevOps em duas camadas; tendências; quatro pilares de valor; modelo de maturidade em 4 estágios.
- Cap. 2, pp. 9-14 — Platform as a Product: plataforma é mais que stack de ferramentas; mindset de produto (feasibility, viability, usability, value); abstrações opcionais e composáveis; envolver stakeholders cedo; brownfield; pensar em anos.
- Cap. 3, pp. 15-19 — Orchestrate, Don't Just Automate: platform façade, limites de pipelines e portais, "puppy for Christmas", automação vs orquestração, user observability, platform decay.
- Cap. 4, pp. 21-24 — Fleet Thinking: gerir serviços/ambientes/infra como frota, lições de OTA automotivo, versionamento, serviços composáveis e atualizáveis.
- Cap. 5, pp. 25-29 — Platform Team Dynamics: três personas (platform engineers, app developers, vendors/producers), platform democracy, multiplayer mode, contribuições sustentáveis.
- Cap. 6, pp. 31-36 — Internal Platform Scorecard: quatro pilares com métricas, baselines, scorecards por estágio de maturidade, armadilhas de medição.
- Cap. 7, pp. 37-40 — The Future of Internal Platforms: open source vs enterprise, "making the mix work", preparação para era AI-native.

## Números

O relatório quase não traz estatísticas; só um caso e os números estruturais abaixo.

| Dado | Valor | Página | Uso sugerido |
|---|---|---|---|
| Seguradora (cliente do Colin Humphreys): ciclo de deploy | de "up to two years" para releases diários | 12, 28 | Slide de impacto: plataforma como produto colaborativo e stakeholders (segurança, compliance) envolvidos cedo |
| Pilares de valor da plataforma | 4 (speed, safety, efficiency, scalability) | 4 | Estrutura do scorecard da IDP |
| Estágios do modelo de maturidade (CNCF Platforms WG) | 4 (ad hoc automation, catalog and portal, orchestrated product, federated ecosystem) | 5-6 | Slide "onde estamos": o portal sozinho é o estágio 2 |
| Métricas-chave do scorecard | 4: MTTFD, SRPC, MTTUSI, MTTASP | 33 | Métricas propostas para a IDP |
| Personas da plataforma | 3 | 25 | Developer, platform team, contributors/producers |
| Casos citados sem detalhe | NatWest, USwitch, Adidas, The Home Depot | 14 | Apenas referência; o relatório não dá números deles |
| Versões em divergência (exemplo) | exemplo v1.2, v1.4 e fork | 23 | Ilustração de "invisible divergence" |
| Metáfora temporal | "day two thousand" | 13, 33 | Longevidade da plataforma |

## Citações

- "A platform is not just a collection of tools, templates, or workflows. It is an evolving system that must continuously respond to user needs." (p. 9)
- "an evolving set of reusable services, integrated with your existing systems, that creates valuable outcomes for your business." — definição de platform product por Colin Humphreys (p. 10)
- "The model is based on enablement rather than enforcement and self-service rather than ticket queues." (p. 3)
- "abstractions should be composable and optional. They should guide without constraining. They should reduce complexity without hiding critical details." (p. 11)
- "Your platform should 'float above' what is already available off the shelf" (p. 11, crédito a Gregor Hohpe)
- "everything is brownfield and complex" (p. 12)
- "Portals are where users interact. Pipelines and workflow engines are execution tools. Orchestration is the system that ties it all together, delivering value across the lifecycle." (p. 19)
- "a polished UI for running fragile automation." — sobre portal sem orquestração (p. 16)
- "Who feeds the puppy?" — o problema "puppy for Christmas" (p. 16)
- "That is not empowerment. That is abandonment." (p. 16)
- "Developers request capabilities, and the platform team governs how those requests are fulfilled." (p. 17)
- "This is not a guide to spinning up a portal or building a golden path." (p. 7)

## Conceitos e frameworks

- Four pillars of platform value: speed, safety, efficiency, scalability, definidos como as "pernas de uma mesa" (pp. 4-5).
- Platform maturity model (CNCF Platforms WG): Stage 1 ad hoc automation, Stage 2 catalog and portal, Stage 3 orchestrated product, Stage 4 federated ecosystem; "not a race to the top but a self-assessment tool"; dois princípios de aceleração: contratos/APIs no centro e baseline nos quatro pilares antes de otimizar um (pp. 5-6).
- DevOps em duas camadas: camada de aplicação e camada de plataforma, consumidas por contratos/APIs bem definidos; plataforma não substitui DevOps (pp. 2-3).
- Product mindset: equilíbrio entre feasibility, viability, usability e value; exige product management, UX design e user research (p. 10). Práticas: colaborar direto com usuários, feedback loops com melhorias pequenas e frequentes, internal brand (p. 11).
- Golden cage: golden path rígido top-down gera shadow platforms; "não existe golden path universal" (p. 11).
- Platform façade: portal + workflow engine/CI sem coordenação, governança e ciclo de vida (p. 15).
- Orquestração: "persistent control layer that coordinates capabilities across the platform, manages state, enforces policy, and enables safe evolution over time" (p. 16). Tabela 3-1 compara automação (pipelines + portais) e orquestração nos quatro pilares (p. 17). Atributos de uma plataforma orquestrada: APIs e contratos claros, requests declarativos com fulfillment automatizado, governança e política compartilhadas, lifecycle awareness e upgrade paths, registro persistente do que foi criado, por quem e por quê (p. 19).
- User observability (Fournier e Nowland): visibilidade de como developers interagem com a plataforma e como seus requests progridem; responde "What happens when I request a new service? Why is my upgrade delayed? Who owns this resource?" (pp. 17-18).
- Platform decay e sintomas (p. 18).
- Fleet thinking / fleet management: gerir coleção de coisas similares mas não idênticas, cada uma com ciclo de vida; analogia com updates OTA de carros (staged, paused, rolled back); versionar capacidades e rastrear o que roda onde (pp. 21-23).
- Invisible divergence: v1.2, v1.4 e um fork sem controle da plataforma (p. 23).
- Três personas: platform engineers, app developers, vendors/producers (internos ou externos) (pp. 25-26). "Platform democracy" (Ted Newman, NatWest) e "multiplayer mode" (Paula Kennedy) (p. 27). Contribuição sustentável: processo claro, frameworks para contribuir, governança de ownership/ciclo de vida/deprecação (p. 28).
- Internal Platform Scorecard, Tabela 6-1 (p. 33): Speed = MTTFD (mean time to first deploy, do request ao serviço rodando); Safety = SRPC (% de serviços rodando em conformidade com a política vigente); Efficiency = MTTUSI (mean time to upgrade service instances, tempo para propagar uma mudança a todas as instâncias vivas); Scalability = MTTASP (mean time to add a service to the platform, da definição do requisito à oferta na plataforma). Indicadores: API-first, golden paths com abstrações composáveis, internal marketplace, workflows guiados por política, upgrades one-click/one-API, drift detection e convergência contínua, multiplayer contribution, inner sourcing.
- Scorecards por estágio: early-stage, mid-stage com adoção crescente, mature/regulated (p. 35).
- Build / buy / borrow como decisão de produto; "treat integration code as part of the platform product" (p. 38). Três mudanças com IA: UIs em linguagem natural/chat sobre APIs existentes, assistentes de orquestração que propõem correções dentro dos guardrails, governança de dados e modelos; plano: fortalecer contratos e metadata, investir em policy e audit, instrumentar tudo, manter humanos no loop, tratar modelos e prompts como artefatos versionados (p. 39).

## Papéis: portal vs orquestrador vs IaC

O relatório cobre a divisão em nível conceitual, sem nomear Kratix nem Promises (a única ligação com Kratix é a bio de Abby Bangser, p. 41). Backstage, Crossplane, Argo Workflows e GitHub Actions aparecem só como exemplos.

- Portal (ex.: Backstage, p. 15): melhora discoverability e oferece entrada amigável; sem orquestração atrás vira "polished UI for running fragile automation" (p. 16). "Portals are where users interact" (p. 19). Um clique que provisiona sem gestão posterior habilita drift e risco (p. 16).
- Pipelines e workflow engines (Argo Workflows, GitHub Actions, p. 15): "execution tools" (p. 19); excelentes para deploys, retries e paralelismo, mas são sistemas transientes que não mantêm estado persistente, política ao longo do tempo nem ownership (pp. 15-16).
- Orquestração: camada de controle persistente (estado, política, ownership, lifecycle); cria separação de concerns entre quem pede e quem governa o fulfillment (pp. 16-17, 19).
- IaC: aparece só como exemplo de componente intercambiável. "run a commercial orchestration engine and integrate it with an open source infrastructure-as-code tool" (p. 38). Terraform modules, cloud APIs e bash scripts devem ficar atrás de uma interface consistente (p. 13). Crossplane e Backstage são citados como projetos CNCF "proven foundations" (p. 38).
- Contratos e APIs permitem trocar implementações sem quebrar workflows de developers (pp. 6, 38).
- O relatório não descreve fluxo ponta a ponta (portal chama orquestrador, que chama IaC), nem cobre Argo CD/GitOps, nem planos de observabilidade/segurança como arquitetura; esse desenho precisa vir de outras fontes.

## Anti-padrões

- Tratar a plataforma como projeto com milestone final e "vague hope" de adoção (p. 9).
- Equipe de plataforma como internal service provider perseguindo feature requests em vez de strategic enabler (p. 9).
- Golden cage / abstrações rígidas e top-down: gera shadow platforms, ferramentas não aprovadas e workarounds (p. 11).
- Reconstruir o que já existe no mercado em vez de "float above" o off-the-shelf; lock-in em uma ferramenta ou workflow (pp. 11-12).
- Envolver segurança, compliance e networking tarde, retrofit de compliance no fim (p. 12).
- Ignorar brownfield: plataforma que só suporta Kubernetes e não cloud APIs, Terraform, scripts e legado (pp. 12-13).
- Exceções pontuais, workarounds permanentes e features bolted on; compartilhar só código, não serviços (p. 13).
- Platform façade: portal + pipeline sem orquestração (p. 15).
- "Puppy for Christmas": provisionar por clique e abandonar o recurso, sem upgrade, política ou lifecycle (p. 16).
- Sealed box: sem user observability, "buttons are clicked, pipelines run, and then... silence", devs voltam a tickets (p. 17).
- Platform decay: ownership e upgrade paths obscuros, workflows que só funcionam em certos ambientes, snowflakes, compliance fragmentada, backlog de "quick fixes" (p. 18).
- Invisible divergence e silent updates sem comunicação nem rollback (p. 23).
- Plataforma como gargalo: platform engineers donos de todas as capacidades, sem vendors/producers (p. 26).
- Integrações one-off e hacks não documentados (p. 28).
- Medir um só pilar antes de ter baseline nos quatro (p. 34).
- Vanity metrics: número de serviços no catálogo, cliques/page views no portal, linhas de YAML (p. 35).
- Só métricas quantitativas, sem surveys e conversas; scorecard como exercício único (p. 35).
- IA como bolt-on experiment (p. 39).
