# Observability Spike: golden signals from a platform-local Prometheus

Issue [#410](https://github.com/smsilva/wasp-idp/issues/410), sub-issue da [#326](https://github.com/smsilva/wasp-idp/issues/326) (golden signals de uma Workload Instance). Decisão registrada no [ADR 0040](../../adr/0040-platform-local-prometheus-scraping-vcluster-sidecars.md). Rodado em 2026-10-12 no k3d `platform-local` (k3s v1.31.5), vcluster chart 0.37.2, Istio 1.30.5, Prometheus v3.5.0.

## Pergunta

A API nunca fala com um vcluster: ela lê só os CRDs no host. Um Prometheus no host, sem nada instalado nos vclusters, consegue calcular os quatro golden signals de uma instância (latência p95, tráfego, erros, saturação)?

## Cenário

- Ambiente `spike-obs` (`--profile shared`), com uma instância de podinfo deployada pela CLI com `dns` e `route` (o mesmo Version do passo #358 do `cli-smoke`), com `resources.limits` de `200m`/`128Mi` no container.
- Tráfego pelo ponto de entrada (`http://spike-obs-app.spike-obs.localhost:7080/`, Traefik → Gateway Istio do vcluster, ADR 0036), com alguns `/status/500` e `/status/503`.
- Prometheus num Deployment só, no namespace `spike-observability` do host, com RBAC `get/list/watch` em `pods`, `nodes`, `nodes/proxy` e `nodes/metrics`, e dois jobs:
  - `sidecars`: `kubernetes_sd_configs` com role `pod`, mantendo só namespaces `env-.+`, label `vcluster.loft.sh/namespace=apps` e `prometheus.io/scrape=true`; o alvo é `<podIP>:15020` no path da anotação. Labels adicionados: `environment` (o namespace sem `env-`), `namespace`, `pod` e `workload_instance` (o label `app.kubernetes.io/instance`).
  - `cadvisor`: o kubelet pelo proxy do apiserver (`/api/v1/nodes/<node>/proxy/metrics/cadvisor`), com `metric_relabel_configs` mantendo só namespaces `env-.+` e cinco métricas (`container_cpu_usage_seconds_total`, `container_memory_working_set_bytes`, `container_spec_cpu_quota`, `container_spec_cpu_period`, `container_spec_memory_limit_bytes`).

## Resultados

**O pod sincronizado no host carrega o que o scrape precisa.** O pod `spike-obs-app-54f48bd6c7-7l7b9-x-apps-x-vcluster` em `env-spike-obs` tem as anotações `prometheus.io/scrape`, `/port` (`15020`) e `/path` (`/stats/prometheus`) postas pelo injector, e os labels do pod do vcluster (`app.kubernetes.io/instance`, `app.kubernetes.io/name`) mais `vcluster.loft.sh/namespace=apps`. Os dois targets ficaram `up`.

**O sidecar é um native sidecar.** O `istio-proxy` vem como initContainer com `restartPolicy: Always`, e a porta `15090` está declarada nele, não no container da app. O service discovery do Prometheus lista os initContainers, então manter o target da porta `15090` dá um alvo por pod.

**As métricas do Istio saem com os nomes do lado do vcluster.** `destination_workload="spike-obs-app"`, `destination_workload_namespace="apps"`, `destination_service_name="spike-obs-app"`. As requisições pelo ponto de entrada chegam com `reporter="destination"` e `source_workload="platform-istio"` (o Gateway). O Istio não conhece o ambiente: ele vem do namespace do host, pelo relabel.

**O cAdvisor dá uso e limite por container.** `container_spec_cpu_quota{container="app"} 20000` com `period` 100000 é o limite de `200m`, e `container_spec_memory_limit_bytes` é o de `128Mi`. As séries não têm o label da instância, só `namespace` e `pod` (o nome do host). O join é por `pod` com o `up` do job `sidecars`, que tem `workload_instance`. Nenhum kube-state-metrics é necessário.

**As quatro consultas**, com a instância selecionada por `environment` e `destination_workload` (janela `5m`):

| Sinal | PromQL | Valor no spike |
|---|---|---|
| latência p95 | `histogram_quantile(0.95, sum by (le) (rate(istio_request_duration_milliseconds_bucket{reporter="destination",...}[5m])))` | 0,49 ms |
| tráfego | `sum(rate(istio_requests_total{reporter="destination",...}[5m]))` | 0,89 req/s |
| erros | a mesma soma com `response_code=~"5.."` sobre o total | 2,2% |
| saturação (CPU) | `rate(container_cpu_usage_seconds_total[5m])` sobre `quota/period`, por pod, `container!~"\|POD\|istio-proxy"`, juntado por `pod` com o `up{job="sidecars",workload_instance=...}`; o maior entre os pods | 0,1% |
| saturação (memória) | `container_memory_working_set_bytes` sobre `container_spec_memory_limit_bytes`, com o mesmo filtro e o mesmo join | 13,1% |

A saturação da instância é o maior entre CPU e memória.

**Custo:** o Prometheus ficou em 30 Mi e 1m de CPU com um ambiente e uma instância.

## Achados

- **O pod sincronizado tem tokens de ServiceAccount em anotações** (`vcluster.loft.sh/token-*`). Elas aparecem como meta labels no service discovery (`__meta_kubernetes_pod_annotation_*`). O relabel nunca pode usar `labelmap` sobre anotações, ou os tokens viram labels gravados no TSDB.
- **A série do pod (`container=""`) soma o `istio-proxy`:** 1.207.959.552 bytes de limite é `128Mi` da app mais `1Gi` do sidecar. A saturação filtra por container (`container!~"|POD|istio-proxy"`), nunca pela série do pod.
- **Sem limite declarado, a saturação não tem denominador.** O spike só rodou com limite; o cAdvisor não publica `container_spec_cpu_quota` para um container sem limite de CPU. A saturação é `null` com o motivo quando falta o limite, e o template `python-service` (que hoje não declara `resources`) passa a declarar.
- **Os labels do Istio têm alta cardinalidade** (`source_principal`, `source_workload`, `response_flags`). Com uma retenção curta e um ambiente local isso não pesa. Um `metric_relabel_configs` que derruba os labels de origem fica para quando o volume crescer.
