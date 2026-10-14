# Istio sidecar per Environment vcluster, routing through GAMMA HTTPRoutes

**Status:** Aceito (2026-10-12)

## Contexto

A fase 3 do Workload Instance (ADR 0033, #295) divide o tráfego do Service de um component entre instâncias: por header no shared sandbox (`x-sandbox: pr-42` → `reviews-pr-42`), por peso no canary. O roteamento é east-west, de um serviço para outro dentro do `Environment`, então um Gateway north-south não basta: é preciso um mesh que implemente GAMMA, o perfil do Gateway API em que um `HTTPRoute` tem como `parentRef` um Service.

Os vclusters dos `Environment`s (provider `local_vcluster`, chart 0.37.2) não têm mesh. O spike ([`docs/superpowers/specs/2026-10-12-mesh-spike.md`](../superpowers/specs/2026-10-12-mesh-spike.md)) comparou Istio sidecar e Linkerd por vcluster com o mesmo `HTTPRoute`: os dois rotearam por header, por baggage e por peso. A integração Istio do vcluster com o mesh no host é Enterprise e só ambient; ambient exige waypoint para L7 e o ztunnel é por nó do host.

## Decisão

**Cada vcluster de `Environment` roda o próprio Istio em modo sidecar, e a plataforma expressa roteamento só como `HTTPRoute` GAMMA.**

- **Istio sidecar, um `istiod` por vcluster.** Linkerd consome menos (~90 Mi contra ~190 Mi no spike), mas não tem release stable open source e exige gerir trust anchor e issuer; o Istio é o mesh que o deck e o ADR 0008 já usam.
- **O `local_vcluster` instala o mesh depois que o vcluster sobe**: CRDs standard do Gateway API, `istio/base` e `istio/istiod`, com os charts embutidos na imagem como o do vcluster, e marca o `Environment` `Ready` só com o `istiod` pronto. Instalar pelo próprio chart do vcluster (`experimental.deploy`) deixa a release do Helm perto do limite de 1 MiB de um Secret.
- **Subsistemas (ADR 0034):** o mesh é parte do `environment`, que garante a qualquer consumidor um vcluster com Istio e Gateway API; a rota é do `workload`, que depende de `environment`. Nenhum dos dois controllers escreve nos CRDs do outro.
- **O namespace `apps` tem injeção de sidecar**, criado pelo provider `workload` com a label `istio-injection=enabled`.
- **A API do Kubernetes do mesh que a plataforma escreve é o `HTTPRoute`**, nunca `VirtualService` ou `DestinationRule`: `parentRef` no Service da instância principal do component, `backendRefs` nos Services das instâncias. A regra é um objeto por component × ambiente, mantido pelo provider `workload` a partir de um CRD da plataforma (#339); a API continua sem escrever no vcluster.

## Consequências

- Cada ambiente custa ~42 Mi de `istiod` e ~50 Mi por pod com sidecar, e sobe ~30 s mais devagar.
- Trocar de mesh muda só a instalação no `local_vcluster`: as rotas são Gateway API.
- As versões do Istio e do Gateway API ficam fixas na imagem do `local_vcluster` e andam juntas (Istio 1.30 → Gateway API 1.5); o Istio 1.30 tem EOL perto de dez/2026.
- Ambientes criados antes desta mudança não têm mesh: a release do vcluster é instalada uma vez. `workload route` num ambiente sem mesh termina com uma condition de erro, não com roteamento silenciosamente ignorado.
- O roteamento por header só vale além da primeira chamada se os serviços repassarem o header; o contrato é o OpenTelemetry Baggage, que o template `python-service` repassa e que está em [`platform/docs/walkthrough/workloads/baggage.md`](../../platform/docs/walkthrough/workloads/baggage.md) (#340).
- Tráfego que entra no ambiente de fora continua fora: quando entrar, o gateway de entrada injeta ou valida o header.
