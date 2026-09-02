# `observability/` — Domain: Observability

Índice de leitura. Convenções e regras ficam em [`CLAUDE.md`](CLAUDE.md).

## O que este domínio entrega

Uma resposta a três perguntas operacionais, para toda a arquitetura hub-and-spoke:

1. **O que aconteceu?** — logs e trilhas (control plane, VPC Flow Logs, CloudTrail, DNS query).
2. **Como está agora?** — métricas (cluster, nodes, TGW, VPN, custo).
3. **Vou ser avisado antes de doer?** — alertas, com ênfase em **conectividade** (túnel VPN
   caindo, attachment do TGW em blackhole, NAT saturado) — o modo de falha próprio do
   hub-and-spoke.

Este é o **último** domínio de propósito: os cinco anteriores constroem a plataforma;
observabilidade é o que permite operá-la com confiança. Ele **não redefine** os sinais que já
vivem em outros domínios (VPC Flow Logs em [`network/06-security.md`](../network/06-security.md), CloudTrail em [`security/06-detection-and-audit.md`](../security/06-detection-and-audit.md),
Budgets em [`accounts/05-billing-and-tags.md`](../accounts/05-billing-and-tags.md)) — ele os **consolida** numa estratégia coerente e adiciona a
camada de compute (Container Insights) e a de conectividade.

## Tópicos

| # | Arquivo | Assunto | Pilar WAF principal |
|---|---|---|---|
| 0 | [`00-strategy.md`](00-strategy.md) | Os 3 sinais (logs/métricas/traces); centralização; onde cada fonte já vive | Operational Excellence |
| 1 | [`01-logs.md`](01-logs.md) | Control plane EKS, container, VPC Flow, CloudTrail, DNS query; retenção e destino | Operational Excellence |
| 2 | [`02-metrics.md`](02-metrics.md) | Container Insights; métricas de TGW/VPN/NAT; Prometheus vs. CloudWatch | Reliability |
| 3 | [`03-connectivity-alerts.md`](03-connectivity-alerts.md) | O modo de falha do hub-and-spoke; alarmes de túnel/attachment/NAT; o que acordar alguém | Reliability |
| 4 | [`04-cost-as-signal.md`](04-cost-as-signal.md) | Budgets, anomaly detection, custo por tag/conta como sinal operacional | Cost Optimization |
| 5 | [`05-crossplane-map.md`](05-crossplane-map.md) | O que de observabilidade é provisionável (add-on/MR) vs. habilitação de conta; estado vs. alvo | — |
