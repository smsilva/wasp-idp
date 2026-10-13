# A platform-local Prometheus scraping the vcluster sidecars

**Status:** Aceito (2026-10-12)

## Contexto

O último momento da jornada do deck (**Run**) mostra os quatro golden signals de uma Workload Instance: `platform workload signals --component greeting-api --environment greetings-test`. Nada na plataforma coleta métricas (#326). O ADR 0034 deixou `observability` como subsistema previsto, sem código (#330, #326).

Duas peças já existem. Cada vcluster de `Environment` roda Istio sidecar (ADR 0035), e o envoy de cada pod em `apps` exporta `istio_requests_total` e `istio_request_duration_milliseconds` em `:15020/stats/prometheus`. E os pods de um vcluster rodam no host como pods sincronizados no namespace `env-<name>`, com os labels e as anotações do pod original.

A API nunca fala com um vcluster: lê só os CRDs no host, e quem alcança o vcluster é o provider `workload`. O spike ([`docs/superpowers/specs/2026-10-12-observability-spike.md`](../superpowers/specs/2026-10-12-observability-spike.md)) calculou os quatro sinais com um Prometheus só, no host, sem nada instalado nos vclusters.

## Decisão

**Um Prometheus no `platform-local`, do subsistema `observability`, coleta os sidecars de todos os ambientes e o cAdvisor do kubelet. A API lê os sinais dele na hora; nenhum CRD guarda métricas.**

- **Instalado pelo `platform init`**, num Deployment em `platform-system` com as labels do ADR 0039 (`provider`, `capabilities=observability`), retenção curta (horas) e sem volume persistente. O mesmo Prometheus recebe o scrape da API e dos providers da #330.
- **Job `sidecars`:** service discovery de pods, só em namespaces `env-.+` com `vcluster.loft.sh/namespace=apps` e `prometheus.io/scrape=true`, alvo `<podIP>:15020`. O relabel adiciona `environment` (do namespace do host), `pod` e `workload_instance` (do label `app.kubernetes.io/instance`), e nunca usa `labelmap` sobre anotações: o pod sincronizado carrega tokens de ServiceAccount em `vcluster.loft.sh/token-*`.
- **Job `cadvisor`:** o kubelet pelo proxy do apiserver, mantendo só namespaces `env-.+` e as métricas de uso e limite de CPU e memória. Sem kube-state-metrics: o join com a instância é por `pod`, com o `up` do job `sidecars`.
- **Os sinais**, por instância e numa janela (padrão `5m`):
  - latência p95 e tráfego de `istio_*` com `reporter="destination"`, o que conta tanto o tráfego que entra pelo ponto de entrada (ADR 0036) quanto o east-west;
  - erros como a fração de `response_code` 5xx;
  - saturação como o maior entre CPU e memória sobre o limite do container, sem o `istio-proxy`, e `null` quando o container não declara limite.
- **A API consulta o Prometheus por HTTP dentro do cluster**, numa rota de leitura de `workload` com o mesmo `can_use` do `get`. Sem o Deployment do Prometheus, a rota responde `503 NoProviderForCapability`. O subsistema `observability` depende de `environment` (o mesh vem dele) e é lido por `workload`.

## Alternativas consideradas

- **O provider `workload` grava um snapshot no status da `WorkloadInstance`.** Cabe na regra de que só ele fala com o vcluster, mas escreve a cada intervalo em todas as instâncias e entrega um número velho. Rejeitada.
- **Um Prometheus por vcluster.** Isola os ambientes, mas custa um processo por ambiente (cada um já paga ~42 Mi de `istiod`) e a API precisaria alcançar cada vcluster. Rejeitada enquanto um Prometheus no host enxerga todos.
- **OpenTelemetry Collector com auto-instrumentação** (#353). Dá traces e métricas da aplicação, mas exige instrumentar o processo; os sinais de borda já saem do sidecar sem tocar na app. Fica para os traces.
- **kube-state-metrics para os limites.** O cAdvisor já publica o limite de cada container (`container_spec_cpu_quota`, `container_spec_memory_limit_bytes`). Desnecessário agora.

## Consequências

- Os sinais só existem para instâncias com sidecar: um pod fora do mesh não aparece.
- O Prometheus custa ~30 Mi com um ambiente; a cardinalidade dos labels de origem do Istio (`source_principal`, `source_workload`) cresce com o número de serviços, e um `metric_relabel_configs` que os derruba é o próximo passo se o volume pesar.
- Sem limite declarado não há saturação: o template `python-service` passa a declarar `resources.limits`.
- Num target em nuvem, a mesma decisão vale com o Prometheus do cluster de controle; o service discovery muda só se os vclusters deixarem de sincronizar pods para o host.
