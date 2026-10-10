# IDP presentation prompt

> Prompt vivo. Para retomar a apresentação numa sessão nova, colar este arquivo e pedir para ler os tópicos em `references/`. Contexto novo entra como um arquivo de tópico novo, referenciado na tabela abaixo — não como texto solto aqui.

## Pedido

Uma apresentação que explique **progressivamente** um Internal Developer Platform (IDP) até o desenho final: os **5 planes** de [`base-deck.md`](base-deck.md), preenchidos com as **tools** da arquitetura de referência, e o que muda quando o usuário da plataforma é um agente.

- Skills: `/presentation-prep` (estrutura cognitiva, YAML por slide) e `/pptx` (geração do `.pptx`, marketplace oficial da Anthropic). Setup: [`../CONTRIBUTING.md`](../CONTRIBUTING.md).
- Pouco texto por slide, mesmo que o deck tenha muitos slides.
- Uma linha de raciocínio encadeada que conduza até o desenho final.
- O modelo do catálogo Backstage é **conteúdo**: a apresentação ensina como o dev declara sua aplicação (Domain, System, Component, API, Resource), com o exemplo de catálogo deste repo (`idp/catalog/communication/`).
- Conteúdo primeiro, num HTML indexado com tópicos e texto de cada slide; visual só depois de aprovado.

## Tópicos

| Arquivo | Conteúdo |
|---|---|
| [`base-deck.md`](base-deck.md) | Deck base, fonte dos 5 planes, tabela plane → categoria → tool |
| [`backstage-catalog.md`](backstage-catalog.md) | Modelo de entidades usado para ensinar o dev a declarar a app; exemplo conhecido (demo do Backstage); por que não guarda versão; catálogo de exemplo deste repo |
| [`backstage-relations.md`](backstage-relations.md) | Relações entre entidades do catálogo: campo do YAML → relação gerada (par automático), três eixos (pertencimento, uso em runtime, responsabilidade), `owner` como único campo obrigatório, API como fronteira. Ainda sem slide |
| [`audiences.md`](audiences.md) | Classificação de slides por público, base do filtro que gera os cortes |
| [`content-rules.md`](content-rules.md) | Regras de conteúdo (presentation-prep + decisões) |
| [`score.md`](score.md) | Score: estrutura do arquivo e como é mostrado (quadro de código estilo IDE, por partes) |
| [`poc.md`](poc.md) | Exemplos concretos da PoC deste repo |
| [`current-state.md`](current-state.md) | MVP 1 (ambiente sob demanda), próximos passos (Platform API, identidade, CLI, portal), sequência do fechamento |
| [`internal-products.md`](internal-products.md) | Internal Products (IP): da ideia ao produto compartilhado; `lifecycle` do Backstage como estado de compartilhamento |
| [`state-of-ai-in-platform-engineering.md`](state-of-ai-in-platform-engineering.md) | Dados e citações do State of AI in Platform Engineering Vol. 2 (Weave Intelligence, 2026) |
| [`platform-as-a-product.md`](platform-as-a-product.md) | Conceitos e citações do report O'Reilly *Platform as a Product* (Syntasso) |
| [`cost-allocation.md`](cost-allocation.md) | Drill down de custo por categoria e entidades do catálogo (Domain, System, Component, Group, User): viabilidade na AWS e no LiteLLM |
| [`sso-dex.md`](sso-dex.md) | SSO: Dex como único OIDC issuer (avaliação inicial, depois substituída por Keycloak), clients, catálogo vs. claim `groups`, identidade imutável, break-glass |
| [`stone-caravela.md`](stone-caravela.md) | Caso Stone (IDP Caravela): NPS e sessões (Hotjar), funis das ofertas e feature flags (Amplitude) |
| [`mercadolibre-fury.md`](mercadolibre-fury.md) | Caso Mercado Livre (IDP Fury): detecta ambiente ocioso e sugere a exclusão ao owner |
| [`empathy-gap.md`](empathy-gap.md) | Artigo "The empathy gap" (platformengineering.org): UX da plataforma, cognitive friction, CLI e erros como UX, sentimento junto com DORA |
| [`platform-illusion.md`](platform-illusion.md) | Artigo "The platform engineering illusion" (platformengineering.com, 2026-07-31): IDP como disciplina de produto, cinco modos de falha, taxa de bypass, pilha de ferramentas ≠ plataforma, segurança no design |
| [`data-ownership.md`](data-ownership.md) | Artigo "Nobody owns the data" (platformengineering.com): dono, contrato e deprecação de dado aplicados pela CI/CD |
| [`adoption-metrics.md`](adoption-metrics.md) | Métricas de adoção do Backstage no Spotify (time to 10th PR: 60 → <20 dias), KPIs da doc oficial, ressalvas |
| [`port-portal-guide.md`](port-portal-guide.md) | Guia da Port (vendor de portal, 2024): plataforma vs. portal, quatro pilares (catálogo, self-service, scorecards, automations), blueprints vs. entidades do Backstage |
| [`formae-cli.md`](formae-cli.md) | CLI do formae como exemplo de expor entidades por CLI: `inventory` por tipo, `--query`, saída humana/máquina, CLI e MCP como clients da mesma API |
| [`configure8-portal-vs-platform.md`](configure8-portal-vs-platform.md) | configure8 (vendor, 2023): definições literais de portal vs. platform; portal como "singular interface" |
| [`internaldeveloperplatform-org.md`](internaldeveloperplatform-org.md) | internaldeveloperplatform.org (ligado à Humanitec): definição de IDP, portal segundo a Gartner, cinco core components, Environment Management |
| [`fitness-functions.md`](fitness-functions.md) | *Fundamentals of Software Architecture* (characteristics) e *Building Evolutionary Architectures* (fitness functions); plataforma e ambientes com fitness functions; exemplos da PoC |
| [`dora-metrics.md`](dora-metrics.md) | As cinco métricas DORA (throughput e instability) e como não usá-las |
| [`golden-signals.md`](golden-signals.md) | Four golden signals do SRE book (latency, traffic, errors, saturation); sintoma vs. causa |
| [`sandbox-routing.md`](sandbox-routing.md) | Verificar antes do PR: CI como gargalo com agents (artigo patrocinado pela Signadot), sandbox por requisição com Istio + OTel Baggage, ambiente completo × sandbox |
| [`mcp-platform-interface.md`](mcp-platform-interface.md) | MCP: spec, primitivas, governança (Agentic AI Foundation), auth OAuth 2.1; Backstage expõe o catálogo como MCP tools (`mcp-actions-backend`, v1.40); vendors com MCP |
| [`agents-md.md`](agents-md.md) | AGENTS.md, CLAUDE.md e Agent Skills como contexto do agente ao lado do código; estudos no arXiv: muda comportamento e custo, não acerto |
| [`dora-ai-report.md`](dora-ai-report.md) | DORA 2025 (fonte primária): IA melhora throughput e ainda aumenta instabilidade; plataforma de qualidade como pré-condição; AI Capabilities Model (7 capacidades) |
| [`dora-roi-ai.md`](dora-roi-ai.md) | DORA ROI of AI-assisted Software Development (2026): IDP como "context provider" e "risk mitigator" para agentes, context layer como primeiro investimento, J-Curve e verification tax |
| [`agent-evals.md`](agent-evals.md) | Evals como suíte de regressão, validation loop, gate humano em ação irreversível; gates determinísticos de plataforma (strict field validation, dry-run, `crossplane resource validate`, Kyverno, OPA, `terraform plan`) |
| [`iterations.md`](iterations.md) | Processo, fases e mecânica de passos do `render-outline` |

## Estrutura

```
docs/presentation/
├─ README.md           o que é e como renderizar
├─ CONTRIBUTING.md     setup da máquina, fluxo de contribuição, campos do outline
├─ idp.yaml            o deck (fonte única)
├─ idp.html            gerado pelo render-outline (versionado)
├─ snippets/           código mostrado nos slides (catalog-info.yaml, app-spec.yaml)
├─ diagrams/           landscape/ e journey/: build.py + SVGs gerados
├─ catalog/idp.yaml    arquitetura de referência como entidades Backstage
├─ references/         PROMPT.md + tópicos
└─ render-outline      YAML → HTML de revisão (valida dependsOn, parts e diagram)
```

## Decisões tomadas

- **Deck único detalhado (2026-10-10):** este repo mantém só a versão detalhada. Versões para outro público (negócio, engenharia) não são copiadas: saem de um filtro sobre `audiences` e `dependsOn` ([`audiences.md`](audiences.md)), para o conteúdo nunca divergir entre cópias.
- **Exemplos deste repo (2026-10-10):** o catálogo de exemplo é o domínio `communication` (`greeter`, `notifier`; `greeting-api` como app da jornada), e os domínios usam `platform.example.com`. O fechamento conta o estado real desta plataforma ([`current-state.md`](current-state.md)).
- **Ferramentas Azure na arquitetura de referência:** a landscape e o catálogo de referência seguem com as tools do deck base (AKS, Azure SQL, Key Vault, Auth0…), enquanto a PoC roda na AWS. Trocar por equivalentes AWS é uma decisão separada.
- **Descritor do catálogo ≠ declaração da app:** o `catalog-info.yaml` (modelo Backstage: quem a app é, dono, sistema, relações) fica em Software Catalog; a App Declaration é a spec de workload no modelo Score (`app-spec.yaml`: do que a app precisa para rodar). Integration & Delivery: Version Control, CI, Registry, Orchestrator, IaC, **Delivery** — IaC provisiona recursos, Delivery entrega a app (GitOps + rollout em anéis).
- **Landscape montada parte a parte:** diagrama progressivo = tipo de slide `diagram` (SVG com `<g data-part>`, `show`/`reveal`), gerado por `diagrams/landscape/build.py`; a landscape começa vazia para não enviesar nem criar expectativa.
- **Jornada pela CLI:** ato `journey`, o `greeting-api` da ideia ao `curl`, um momento por slide (Plan, Code, Build, Environment, Release, Run) com um terminal que revela um comando por passo (`diagrams/journey/build.py`). Forma da CLI: `platform <recurso> <verbo>` (`app`, `build`, `environment`, `release` × `create`/`list`), app como escopo `--app`, release devolve a URL — padrão de `gh`, `gcloud`, `fly`, `heroku`; opções longas, um argumento por linha. Comandos ilustrativos.
- Fonte única em YAML; o HTML é gerado e versionado junto (regerar antes de commitar).
- Slides identificados por `name` (slug), não por número — reordenar não quebra referências.
- Públicos: `executive`, `engineering`, `platform`.
- Exemplos de código (Score, `catalog-info.yaml`) aparecem como quadro estilo IDE, em partes com foco por slide (`code: {file, lines, focus}` no outline).
- A ordem dos planes na narrativa (jornada de um pedido) é escolha nossa; a fonte (platformengineering.org) os apresenta como camadas paralelas.
- Idioma: tudo o que aparece na tela em inglês (keywords, `heading`, `topic`, títulos e perguntas de ato); notas e fala em pt-BR.
- **Abertura como jornada compartilhada:** o slide `title` diz que construir o IDP é uma jornada com objetivos claros, não um desenho a entregar.
- **Objetivo é ideia → produto:** o ato `problem` parte de um cenário comum (times de infraestrutura cuidam da infra, mas pedir é burocrático; um ambiente completo por cliente é caro para quem só quer um gateway de modelos). O objetivo vai além do MVP 1: qualquer pessoa leva uma ideia a Internal Product, e o `lifecycle` do catálogo marca quando ele é compartilhado ([`internal-products.md`](internal-products.md)).
- O ato "problema" usa o dado +6 vs. +24 p.p. (State of AI, p. 21: agentes sem reconstruir a plataforma vs. reconstruindo). As ressalvas ficam nas notas: dado autorrelatado e amostra pequena no Level 3 (n = 50).
- O slide do orquestrador usa "platform façade" (*Platform as a Product*, p. 15: portal + pipeline sem orquestração) para responder "por que não basta portal + CI?". O viés da fonte (patrocínio da Syntasso) fica nas notas.
- **IA como fio condutor, não bloco à parte:** o arco termina em "IDP para humanos e agentes". Os cinco planes viram a tooling layer do Agentic Engineering Platform, e o ato `agentic` acrescenta as camadas de paths e agent infrastructure. A tese vem do DORA ROI (p. 40: o IDP é "the risk mitigator and the context provider for AI agents"); o State of AI dá o modelo de camadas e de maturidade.
- **AGENTS.md entra com ressalva, não como argumento:** os estudos não mostram ganho de acerto, só de eficiência ([`agents-md.md`](agents-md.md)). A mensagem é contexto curto e gerado pelo golden path.
- **Transição de tópico:** cada mudança de `topic` ganha um passo de transição gerado pelo `render-outline` (ato + tópico em destaque). Não vira slide no YAML; o índice e a numeração de slides não mudam, só a de passos.
- **Orquestrador:** Crossplane como motor e um resolvedor (controller) que escolhe o modo de cada recurso — `provision`, `compose` ou `bind` (ADR 0022). Substitui a pergunta "Kratix e Crossplane?".

## Perguntas em aberto

- **Filtro por público:** como o `render-outline` gera os cortes (flag `--audience`, um YAML de corte que lista atos/slides, ou os dois) e se a página inicial com a lista de cortes volta junto.
- **Ideias guardadas:** o slide "One CLI, every plane" (um terminal com 2 comandos ilustrativos por plane) saiu porque a jornada ponta a ponta mostra a CLI melhor; o desenho segue em `diagrams/landscape/cli.svg` (gerado por `build.py`, `CLI_GROUPS`) para reaproveitar.
- Demo ao vivo: mostrar os conceitos do catálogo no Backstage deste repo (`idp/`) durante a apresentação. Não decidido.
