# Adoption metrics

Métricas de adoção e sucesso do Backstage publicadas pelo Spotify. Uso: referência para medir a adoção da **plataforma** (não só do portal).

## Fontes

- **Doc oficial do Backstage, "Strategies for adopting", seção "KPIs and metrics":** <https://backstage.io/docs/overview/adopting/> — é a parte da documentação que lista as métricas (fonte em `docs/overview/adopting.md` no repositório `backstage/backstage`).
- **Blog do Spotify, "How we measure Backstage success at Spotify":** Helen Greul, 2021-10-18 (atualizado em 2026-06-30). <https://backstage.spotify.com/discover/blog/measuring-backstage-success-at-spotify>
- InfoQ, "Spotify Reveals Metrics for Success of Developer Portal Backstage": Matt Saunders, 2023-04-24. <https://www.infoq.com/news/2023/04/spotify-success-backstage/>

## Métrica norte: onboarding time

- Doc oficial: "Onboarding time — Time until new engineers are productive. At Spotify we measure this as the time until the employee has merged their 10th PR (this metric was down 55% two years after deploying Backstage)."
- Blog do Spotify: o "time-to-merge your 10th pull request" tinha chegado a **60 dias** e caiu para "less than 20 days for a new joiner to merge their 10th PR". O blog também diz que a métrica é um bom proxy da complexidade geral do ecossistema, mesmo para quem não contrata no ritmo do Spotify.
- **Os números não fecham entre si:** 60 → menos de 20 dias é queda de mais de 66%; a doc fala em 55% "two years after deploying". Provavelmente são medições de momentos diferentes. Citar sempre a fonte e a data do número usado.
- Ressalva da própria Pia Nilsson (ex-líder de Platform Developer Experience no Spotify), em palestra na InfoQ: não é uma métrica fantástica e falta nuance — foi copiada da Meta. Usar como direção.

## Demais KPIs da doc oficial

- Number of merges per developer/day (menos troca de ferramenta, mais tempo codando).
- Deploys to production (frequência como proxy de produtividade).
- MTTR (achar a causa raiz mais rápido com as ferramentas integradas).
- Context switching: "the number of different tools an engineer has to interact with" para concluir uma tarefa.
- T-shapedness: capacidade de contribuir em domínios diferentes graças à infraestrutura consistente.
- eNPS: pesquisa de satisfação sobre produtividade e ferramentas.
- Fragmentation: variância de escolhas tecnológicas entre componentes, como medida de padronização.

## Proxy metrics (adoção do próprio portal)

- Doc oficial (números podem estar desatualizados): 63 times contribuíram com pelo menos um plugin; 135 plugins no total; 85% das contribuições de fora do time central; cerca de 50% de todos os funcionários usam o Backstage por mês.
- Blog do Spotify (atualizado): "86% of internal users are satisfied with Backstage"; "80% of contributions are from outside the core team"; "150+ plugins contributed from 100+ squads"; "Most Spotify engineers visit Backstage on a daily basis"; busca medida por "search success rates, click-through rates, and search results relevance".
- O blog também avisa: "there is no universal answer on how to measure Backstage success" — escolher métricas alinhadas aos objetivos de cada organização.
- InfoQ: o Spotify mede produtividade, eficiência e efetividade do dev; engajamento por usuários únicos, frequência de visita e tempo no portal; satisfação por pesquisas no plugin Pulse.

## Não verificado

- "Usuários frequentes 2,3x mais ativos no GitHub, deploy duas vezes mais frequente, mudanças 17% mais rápidas": aparece em resumos de busca atribuído à InfoQ (2023), mas não foi encontrado no texto do artigo. Não usar até achar a fonte primária.
- "Adoção média do Backstage fora do Spotify em torno de 10%": atribuído a falas do Spotify em reportagem da TechTarget; não conferido.

## Uso na apresentação

- **Métrica norte da plataforma:** "quantos dias um dev novo leva para levar uma mudança até produção" — medida de complexidade do ecossistema, não de uso do portal.
- Contrasta com vanity metrics (Platform as a Product, p. 35: serviços no catálogo, page views) e combina com o scorecard do mesmo report (MTTFD — mean time to first deploy) e com o caso Stone (NPS + funis).
- Candidata natural: tempo do pedido de um `Environment` até o primeiro uso do LiteLLM pelo Claude Code.
