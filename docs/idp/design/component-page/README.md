# Component Page Redesign

Mockups da fase 1 do redesign visual do Backstage (#128): só a página de Component, com os dados reais de `component:default/greeting-api` (catálogo, Kubernetes e repo `wasp-foundry/greeting-api` em 2026-10-03). Nada aqui altera `idp/packages/app`.

Os arquivos são HTML autocontidos no formato de artifact do claude.ai (sem `<html>`/`<body>`), mas abrem direto no navegador. Cada um tem as abas Overview, APIs, Dependencies, Kubernetes e Docs, modo claro e escuro, e um bloco "Notas de design" com o que muda em relação à página atual.

| Proposta | Arquivo | Ideia |
|---|---|---|
| A — Refined | [`a-refined.html`](a-refined.html) | Evolução implementável com MUI/BUI: descrição no header, breadcrumb Domain → System, abas com contagem, Overview começando pelos ambientes, dependências agrupadas por papel, seções vazias escondidas |
| A — Refined, versão inicial | [`a-refined-initial.html`](a-refined-initial.html) | Recorte da A que sai só do que já existe (catálogo, plugin Kubernetes, catalog-graph, api-docs, TechDocs): sem aba Environments, sem Latest commit/Language da API do GitHub; "Running version" vem das imagens dos pods |
| B — Console | [`b-console.html`](b-console.html) | Dark-first: coluna de identidade fixa, linha de status, trilha de entrega commit → imagem → dev → prod, topologia em colunas, atalhos de teclado nas abas |

## Problemas da página atual que as duas atacam

- Descrição repetida (card About e card Description).
- Grafo de relações ocupando metade da primeira tela.
- Tabelas vazias de "Depends on components" e "Has subcomponents".
- Clusters misturados com banco, fila e bucket em "Depends on resources", com coluna Lifecycle sempre vazia e descrições truncadas.
- Aba Kubernetes escondendo pod, imagem e restarts atrás de um expand.

## Dados que vêm de fora do catálogo

Linguagem, último commit e comparação dev × prod não estão no catálogo hoje: exigem leitura do GitHub ou das imagens dos pods. A proposta B depende mais disso do que a A.
