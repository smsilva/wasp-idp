# 05 — Crossplane Map

> O que de observabilidade é provisionável (add-on/MR) vs. o que é habilitação de conta, o
> estado atual do PoC e o gap até o alvo. Fecha o domínio — e o conjunto dos seis.

## O que é provisionável — e o que é habilitação de conta

Observabilidade se divide em duas naturezas de provisionamento:

| Peça | Como se materializa | Provisionável via Crossplane? |
|---|---|---|
| **Container Insights / agente** | add-on no cluster (`amazon-cloudwatch-observability`) + Pod Identity | ✅ MR (mesmo padrão de add-on — [`compute/02-addons-and-identity.md`](../compute/02-addons-and-identity.md)) |
| **Control plane logging** | flag no recurso EKS (`enabledClusterLogTypes`) | ✅ campo do MR do cluster |
| **VPC Flow Logs** | `FlowLog` na VPC | ✅ MR ([`network/`](../network/)) |
| **CloudWatch Alarms** | `MetricAlarm` + `SNSTopic` | ✅ MR |
| **Budgets / Anomaly Detection** | recurso de conta (`Budget`) | ⚠️ possível, mas é escopo de conta/gerência |
| **CloudTrail / GuardDuty / Access Analyzer** | habilitação de Organization/conta | ⚠️ conta de gerência, não o Crossplane do spoke |
| **Log retention / destinos cross-account** | política de log group + destination | ⚠️ parcial; centralização é conta de observabilidade |

A linha: o que é **do spoke** (add-on, Flow Log, alarme) o Crossplane do cluster provisiona; o
que é **da Organization/conta central** (CloudTrail org-wide, GuardDuty, centralização
cross-account) é habilitação na conta de gerência/observabilidade — fora do Crossplane do
spoke, coerente com [`accounts/06-crossplane-map.md`](../accounts/06-crossplane-map.md) e [`security/07-crossplane-map.md`](../security/07-crossplane-map.md).

## O padrão de add-on de observabilidade

Container Insights segue o **mesmo molde canônico** dos outros add-ons ([`compute/02-addons-and-identity.md`](../compute/02-addons-and-identity.md)):

```text
Fase de identidade:  Role <prefix>-cloudwatch-role (policy CloudWatchAgentServerPolicy) + PodIdentityAssociation
      ↓ (esperar Ready)
Fase de workload:    Addon amazon-cloudwatch-observability (ou Release do agente)
```

A mesma disciplina "identidade precede workload" que evita a race — não é diferente por ser
observabilidade.

## Alarmes como código

Os alarmes de conectividade (`03`) são `MetricAlarm` + `SNSTopic` declarativos — versionáveis
como qualquer MR. O alvo é que cada spoke, ao subir, já traga seu conjunto de alarmes baseline
(NAT, node, e — quando houver TGW/VPN — tunnel/blackhole), compostos junto do `Cluster`
([`compute/06-crossplane-map.md`](../compute/06-crossplane-map.md)) ou de um XR de observabilidade dedicado.

## Estado atual do PoC vs. alvo

| Peça | Estado no PoC | Alvo |
|---|---|---|
| Leitura de logs/métricas | ✅ via `eks-mcp-server` (CloudWatch Logs/Insights, métricas, eventos, pod logs) | mantém + painéis |
| Control plane logging | ⚠️ opt-in, não garantido no baseline | `audit`+`authenticator` ligados por padrão |
| Container Insights | ❌ não habilitado por padrão | add-on + Pod Identity (padrão canônico) |
| VPC Flow Logs | ⚠️ mapeado ([`network/06-security.md`](../network/06-security.md)), não confirmado ligado | `FlowLog` por spoke |
| CloudWatch Alarms (conectividade) | ❌ não existem (sem TGW/VPN ainda) | `MetricAlarm`+`SNS` baseline por spoke |
| Budgets / Anomaly Detection | ⚠️ mapeado ([`accounts/05-billing-and-tags.md`](../accounts/05-billing-and-tags.md)), não configurado | por conta/tag, na gerência |
| Centralização cross-account | ❌ conta única | conta de observabilidade (quando [`accounts/`](../accounts/) separar) |
| Prometheus/Grafana | ❌ não usado | Amazon Managed Prometheus/Grafana p/ métrica de app (alvo) |

## Ordem de adoção sugerida

1. **Ligar o baseline barato agora:** control plane logging (`audit`/`authenticator`) +
   Container Insights (add-on + Pod Identity) no cluster atual.
2. **VPC Flow Logs** por spoke (`FlowLog` MR).
3. **Alarmes de compute/NAT** (`MetricAlarm`+`SNS`) — o que já dá para medir sem TGW/VPN.
4. **Quando TGW/VPN existirem** ([`network/07-crossplane-map.md`](../network/07-crossplane-map.md), Gap 2): alarmes de tunnel state / blackhole.
5. **Quando [`accounts/`](../accounts/) separar contas:** centralização cross-account + Budgets/Anomaly na
   gerência.
6. **Prometheus gerenciado** quando a aplicação exigir métrica custom/dashboards ricos.

## Fecho do conjunto

Este é o sexto e último domínio. Com ele, `aws/docs/` cobre a arquitetura de referência
completa: **accounts** (onde), **network** (por onde), **security** (quem pode), **dns** (como
se acha), **compute** (onde roda) e **observability** (como se enxerga). O próximo passo do
projeto não é mais documentação de referência, e sim **retomar o schema detalhado e a spec de
implementação** ([`network/07-crossplane-map.md`](../network/07-crossplane-map.md), [`compute/06-crossplane-map.md`](../compute/06-crossplane-map.md)) — ver o `HANDOFF.md`.
