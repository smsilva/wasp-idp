# Stone Caravela

Caso real de IDP tratado como produto: a Stone mede satisfação e uso da plataforma e controla rollout de funcionalidades com ferramentas de produto. Fonte: live no YouTube, <https://www.youtube.com/live/xACNR0cBzTQ> (timestamps abaixo). Resumo fornecido pelo usuário em 2026-10-07; conferir no vídeo antes de citar detalhe na tela.

- IDP da Stone: **Caravela**.

## Satisfação e uso (product analytics)

- **Hotjar** (31:05–35:00): feedback qualitativo e quantitativo. NPS com pesquisas disparadas em momentos-chave; gravações de sessão para achar atrito e frustração na jornada do dev; análise de cliques para melhorar a usabilidade.
- **Amplitude** (35:30–43:00): dados quantitativos. Funis de conversão das "ofertas" (templates de provisionamento) para achar onde o dev desiste e otimizar o fluxo.

## Feature toggles

- **Amplitude Experiment** (59:00–1:03:00): feature flags e testes A/B. SDK integrado ao IDP; hooks no frontend condicionam o comportamento da funcionalidade. Rollout gradual sem segurar release no fluxo de desenvolvimento.

## Uso na apresentação

- Exemplo concreto de "plataforma como produto": produto tem usuário, mede satisfação e conversão, e lança funcionalidade de forma gradual.
- Liga com *user observability* (Platform as a Product, pp. 17-18: "What happens when I request a new service?") e com a armadilha das vanity metrics (p. 35: contar serviços no catálogo ou page views do portal não mede valor). O funil de uma oferta mede o caminho do pedido até o uso, não o clique.
