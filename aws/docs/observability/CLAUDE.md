# CLAUDE.md — `observability/` (Domain: Observability)

> Índice do domínio de **Observabilidade** — a camada transversal que torna todos os outros
> domínios **visíveis**: o que trafega, o que consome recurso, o que está prestes a falhar.
> Ordem de leitura = ordem dos arquivos. Corpo genérico (placeholders `<...>`).

## O que este domínio entrega

Uma resposta a três perguntas operacionais, para toda a arquitetura hub-and-spoke:

1. **O que aconteceu?** — logs e trilhas (control plane, VPC Flow Logs, CloudTrail, DNS query).
2. **Como está agora?** — métricas (cluster, nodes, TGW, VPN, custo).
3. **Vou ser avisado antes de doer?** — alertas, com ênfase em **conectividade** (túnel VPN
   caindo, attachment do TGW em blackhole, NAT saturado) — o modo de falha próprio do
   hub-and-spoke.

Este é o **último** domínio de propósito: os cinco anteriores constroem a plataforma;
observabilidade é o que permite operá-la com confiança. Ele **não redefine** os sinais que já
vivem em outros domínios (VPC Flow Logs em `../network/06`, CloudTrail em `../security/06`,
Budgets em `../accounts/05`) — ele os **consolida** numa estratégia coerente e adiciona a
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

## Sequência de construção (plataforma → plataforma observável)

```text
① Logs sempre ligados: control plane EKS, CloudTrail (../security), VPC Flow Logs (../network)
② Container Insights no cluster → métricas de node/pod em CloudWatch
③ Métricas de conectividade: TGW, VPN tunnel state, NAT bytes → CloudWatch
④ Alarmes de conectividade (túnel down, blackhole, NAT saturado) → notificação
⑤ Custo como sinal: Budgets + anomaly detection por conta/tag (../accounts/05)
⑥ (alvo) Painéis centralizados e correlação cross-domínio
```

## Estado atual vs. alvo (resumo)

- **Hoje no PoC:** observabilidade é **pontual e sob demanda** — logs do control plane e de
  pods consultáveis (o `eks-mcp-server` lê CloudWatch Logs/Insights, eventos K8s, pod logs);
  CloudTrail protegido por SCP. Não há painel central, nem alarme de conectividade (não há TGW/VPN
  ainda), nem Container Insights habilitado por padrão.
- **Alvo desta referência:** os três sinais ligados por padrão em cada spoke, com **alarmes de
  conectividade** (o que o hub-and-spoke exige) e custo como sinal — consolidados, não
  espalhados.
- **Gap central:** os alarmes de conectividade só fazem sentido quando TGW/VPN existirem
  (`../network/07`, Gap 2) — hoje são mapa; o que já dá para ligar é logs + Container Insights.

## Relação com o resto do repo

- **Consolida** sinais de `../network/06` (VPC Flow Logs), `../security/06` (CloudTrail,
  GuardDuty, Access Analyzer), `../dns/05` (query logging) e `../accounts/05` (Budgets) — este
  domínio os organiza, não os reinventa.
- **Adiciona** a camada de compute (Container Insights, `../compute/`) e de conectividade
  (TGW/VPN, `../network/03-04`).
- **Código/ferramenta:** o `eks-mcp-server` (CloudWatch Logs/Insights, métricas, eventos) é a
  interface de leitura já usada no PoC — apêndice.
