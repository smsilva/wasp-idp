# 01 — Logs

**Pilar WAF principal:** Operational Excellence (a trilha do que aconteceu) + Security ([SEC04 — Detection](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/detection.html)).

## As fontes de log da arquitetura

Cada camada produz um tipo de log; juntos, respondem "o que aconteceu" em qualquer nível:

| Fonte | O que registra | Onde nasce | Já documentado em |
|---|---|---|---|
| **Control plane EKS** | api, audit, authenticator, scheduler, controllerManager | control plane (opt-in) | [`compute/00-cluster-as-spoke.md`](../compute/00-cluster-as-spoke.md) |
| **Container / aplicação** | stdout/stderr dos pods | nodes → CloudWatch (Fluent Bit/Container Insights) | [`compute/`](../compute/) |
| **VPC Flow Logs** | o que trafegou (aceito/negado) por ENI/subnet/VPC | VPC de cada spoke | [`network/06-security.md`](../network/06-security.md) |
| **CloudTrail** | toda chamada de API (quem, o quê, quando) | Organization | [`security/06-detection-and-audit.md`](../security/06-detection-and-audit.md) |
| **DNS query logging** | o que foi resolvido (público e Resolver) | Route53 | [`dns/05-security.md`](../dns/05-security.md) |

Este tópico não reexplica cada um (os links têm o detalhe) — organiza **destino, retenção e
para que servem juntos**.

## Control plane logging — opt-in, ligar cedo

Os logs do control plane EKS (`api`, `audit`, `authenticator`, `controllerManager`,
`scheduler`) são **opt-in** — o cluster nasce sem eles. Ligar cedo importa porque:

- **`audit`** é a trilha de quem fez o quê **dentro** do cluster (o par K8s do CloudTrail) —
  essencial para investigar RBAC ([`compute/03-access-and-rbac.md`](../compute/03-access-and-rbac.md)) e ação de workload.
- **`authenticator`** mostra falhas de mapeamento IAM→RBAC — o sintoma do "creator sem admin"
  ([`compute/03-access-and-rbac.md`](../compute/03-access-and-rbac.md)) aparece aqui.

Vão para CloudWatch Logs; habilitar ao menos `audit` + `authenticator` como baseline.

## Destino e retenção

```text
Logs de curto prazo (operação/debug)   → CloudWatch Logs   (retenção 7-30 dias, busca rápida)
Logs de longo prazo (auditoria/forense) → S3               (barato, retenção meses/anos)
```

- **CloudWatch Logs** para o que se consulta no dia a dia (Insights, correlação rápida). Definir
  **retenção explícita** por log group — o default é "nunca expira", que vira custo silencioso.
- **S3** (via export ou log destination) para retenção longa e barata — CloudTrail e Flow Logs
  de auditoria cabem aqui.
- **Coerência multi-account:** centralizar num destino comum (`00`) — no PoC (conta única) é
  local; no alvo, cross-account.

## CloudWatch Logs Insights — a consulta

A leitura prática de logs é via **Logs Insights** (query sobre log groups): filtrar por
período, padrão (`ERROR`, `AccessDenied`), campo. É a interface que o `eks-mcp-server` usa para
`get_cloudwatch_logs`/`get_pod_logs` no PoC — buscar por recurso (pod/node) e janela de tempo,
sem baixar o log inteiro.

## Correlação — o valor está em cruzar

Um incidente raramente se explica por uma fonte só. O destino comum permite cruzar:

```text
"App X ficou sem responder às 14h"
  container log  → a app logou timeout ao chamar a AWS
  VPC Flow Log   → tráfego para o NAT foi negado/dropado
  CloudTrail     → alguém alterou o SG às 13h58
  →  causa: mudança de SG cortou a saída. Uma fonte só não contava a história.
```

É por isso que o baseline liga **todas** as fontes por padrão, mesmo as que "parecem
desnecessárias" até o dia do incidente ([SEC04-BP01 — Configure service and application logging](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_detect_investigate_events_app_service_logging.html): sem o log, a violação é invisível).

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **[OPS08-BP01 — Analyze workload metrics](https://docs.aws.amazon.com/wellarchitected/latest/operational-excellence-pillar/ops_workload_observability_analyze_workload_metrics.html)** | control plane + container + Flow + CloudTrail + DNS, todos ligados |
| **[OPS08-BP04 — Create actionable alerts](https://docs.aws.amazon.com/wellarchitected/latest/operational-excellence-pillar/ops_workload_observability_create_alerts.html)** | destino comum permite cruzar fontes num incidente |
| **[SEC04-BP01 — Configure service and application logging](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_detect_investigate_events_app_service_logging.html)** | audit/authenticator do control plane + CloudTrail |
| **COST** retenção consciente | CloudWatch curto prazo + S3 longo prazo; retenção explícita por log group |

## Próximo

→ [`02-metrics.md`](02-metrics.md): os números — cluster, conectividade e como coletá-los.
