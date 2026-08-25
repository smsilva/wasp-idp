# 02 — Métricas

**Pilar WAF principal:** Reliability (saber a saúde antes de degradar) + Operational Excellence.

## Duas famílias de métrica

| Família | Nasce em | Coletada por | Exemplo |
|---|---|---|---|
| **Infra AWS** | serviços AWS (EKS, TGW, VPN, NAT, ELB) | **CloudWatch** (nativo) | tunnel state, `BytesOutToDestination` do NAT |
| **Cluster / aplicação** | nodes, pods, apps | **Container Insights** (→ CloudWatch) e/ou **Prometheus** | CPU/memória de pod, latência de app |

Regra prática (do `00`): métrica de **infra AWS** tende a CloudWatch (é onde nasce, de graça);
métrica de **aplicação** tende a Prometheus/Grafana. Não competem — cobrem camadas distintas.

## Container Insights — a saúde do cluster em CloudWatch

**Container Insights** coleta métricas de node/pod/serviço do EKS e as publica no namespace
CloudWatch `ContainerInsights`. É o baseline de compute:

- Métricas por **cluster, node, pod, namespace, service** — CPU, memória (`memory_rss`),
  rede (`network_rx/tx_bytes`), contagem de pods.
- **Dimensões importam:** consultar exige a dimensão certa (ClusterName + PodName + Namespace).
  Cuidado com `FullPodName` (tem sufixo aleatório de revisão) vs. `PodName` (estável) — usar o
  estável para agregar. É a interface que o `eks-mcp-server` expõe (`get_cloudwatch_metrics`,
  `get_eks_metrics_guidance`).
- **Stat certo por métrica:** `Average` para CPU, `Maximum` para picos de memória, `Sum` para
  taxas de rede — casar o estatístico ao que a métrica significa.

## Métricas de conectividade (a base do tópico 3)

O hub-and-spoke tem métricas próprias, em CloudWatch, que alimentam os alarmes de conectividade:

| Recurso | Métrica-chave | Sinaliza |
|---|---|---|
| **VPN (site-to-site)** | `TunnelState` (1=up, 0=down) por túnel | túnel caído → risco de perder HA |
| **VPN** | `TunnelDataIn/Out` | tráfego real por túnel (ECMP distribuindo?) |
| **Transit Gateway** | `BytesIn/Out`, `PacketDropCount*` (blackhole/no-route) | attachment sem rota → isolamento quebrado ou tráfego caindo |
| **NAT Gateway** | `BytesOutToDestination`, `ErrorPortAllocation` | NAT saturando (custo e falha de saída) |

Essas métricas **só existem quando TGW/VPN existirem** (`../network/07`, Gap 2) — hoje são mapa;
o que já dá para medir é o NAT do spoke atual e o cluster.

## Prometheus vs. CloudWatch — quando cada um

| | **CloudWatch / Container Insights** | **Prometheus / Grafana** |
|---|---|---|
| Métrica de infra AWS | nativa, grátis | precisa de exporter |
| Métrica de aplicação (custom) | via embedded metrics / custom | nativa (`/metrics`, PromQL) |
| Dashboards | CloudWatch dashboards (simples) | Grafana (ricos, PromQL) |
| Gerenciado | sim | **Amazon Managed Prometheus/Grafana** (evita operar o stack) |

Alvo pragmático: **CloudWatch** para infra e um baseline de cluster (Container Insights);
**Prometheus** (idealmente gerenciado) quando a aplicação exigir métrica custom e dashboards
ricos. O PoC hoje lê CloudWatch via `eks-mcp-server`; Prometheus é alvo (apêndice).

## SLIs/SLOs — do sinal ao objetivo

Métrica crua vira operação quando ancorada em objetivo:

- **SLI** (indicador) — ex.: % de requests 2xx, latência p99.
- **SLO** (objetivo) — ex.: p99 < 300ms em 99.9% do mês.
- O alarme (tópico 3) dispara contra o **SLO/limiar**, não contra o número cru — evita alerta
  por ruído. Definir SLO por serviço é alvo; o baseline é ter a métrica para poder defini-lo.

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **[REL06-BP01](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_monitor_aws_resources_monitor_resources.html)** monitorar componentes | Container Insights (cluster) + CloudWatch (TGW/VPN/NAT) |
| **[OPS08-BP01](https://docs.aws.amazon.com/wellarchitected/latest/operational-excellence-pillar/ops_workload_observability_analyze_workload_metrics.html)** métricas de negócio e técnicas | infra em CloudWatch, aplicação em Prometheus |
| **REL** capacidade | NAT/tunnel/node metrics antecipam saturação |
| **OPS** medir para melhorar | SLI/SLO ancoram alarme em objetivo, não em ruído |

## Próximo

→ [`03-alertas-de-conectividade.md`](03-alertas-de-conectividade.md): transformar métrica em
aviso — o modo de falha do hub-and-spoke.
