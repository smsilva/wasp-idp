# 04 — Cost as Signal

**Pilar WAF principal:** Cost Optimization ([COST02 — Governance](https://docs.aws.amazon.com/wellarchitected/latest/cost-optimization-pillar/governance.html)/[COST05 — Evaluate cost when selecting services](https://docs.aws.amazon.com/wellarchitected/latest/cost-optimization-pillar/evaluate-cost-when-selecting-services.html)).

## Custo é telemetria, não só fatura

Numa arquitetura com **custo por hora fixo** (control plane EKS, NAT Gateway, TGW attachments,
VPN Connections, EIPs), a fatura é um **sinal operacional** como CPU ou latência: um desvio
inesperado quase sempre significa algo errado (um recurso órfão, um NAT saturando, um cluster
que ninguém destruiu). Tratar custo como métrica — com alarme — é parte da observabilidade,
não um assunto separado de FinOps.

Este tópico não redefine Budgets/tags (isso é [`accounts/05-billing-and-tags.md`](../accounts/05-billing-and-tags.md)) — mostra como usá-los **como
sinal** e como o custo se correlaciona com os outros dados.

## Budgets como alarme (o baseline)

**AWS Budgets** por conta ou por tag, com alerta em thresholds (80%/100% do orçamento mensal),
é a rede de segurança contra o custo silencioso:

- **Por conta** — cada projeto tem seu teto; estourar avisa o dono (`owner` tag).
- **Por tag** — granularidade dentro da conta (`environment`, `owner` — [`accounts/05-billing-and-tags.md`](../accounts/05-billing-and-tags.md)).
- **Recursos de custo fixo** desta referência que justificam o alarme: NAT Gateway, control
  plane EKS, TGW/VPN (quando existirem — [`network/00-topology.md`](../network/00-topology.md),`04`), EIPs. "Esqueci um NAT rodando"
  é exatamente o que o Budget pega.

## Cost Anomaly Detection — o desvio que você não previu

Budget pega o que você **definiu** um teto. **Cost Anomaly Detection** pega o que você **não
previu**: usa ML sobre o histórico e alerta quando o gasto foge do padrão (um serviço que
dobrou de um dia para o outro), sem você ter configurado um limiar para ele.

- Complementa o Budget: Budget é limiar fixo; Anomaly Detection é desvio relativo ao padrão.
- Roteia para o mesmo canal de alerta (SNS, `03`) — custo anômalo é um "alarme" como outro
  qualquer.

## Correlação: custo × conectividade × compute

Custo raramente sobe sozinho — cruzar com os outros sinais aponta a causa:

```text
Alarme: custo de NAT do spoke A subiu 3×
  → métrica NAT (02): BytesOut disparou
  → VPC Flow Logs (../network/06): quem está gerando a saída? (pod X batendo numa API externa em loop)
  → causa: bug de retry, não crescimento real. Custo foi o SINAL; o log deu a causa.
```

Outro padrão: **VPC endpoints** ([`network/06-security.md`](../network/06-security.md)) reduzem custo de NAT — se o NAT sobe, pode
ser sinal de que um serviço deveria estar indo por endpoint privado e não está.

## Custo por conta/tag — a visão que a estrutura já dá

Coerente com [`accounts/05-billing-and-tags.md`](../accounts/05-billing-and-tags.md): a **conta por projeto** já separa custo nativamente (Cost
Explorer por `linked account`); as **tags** (`project`, `environment`, `owner`, `managed-by`)
dão granularidade abaixo da conta. Para observabilidade, o valor é poder responder "de quem é
este custo?" na hora do alarme — a tag `owner` é o contato.

## O custo do próprio observability

Observabilidade tem custo (ingestão de logs, métricas custom, retenção). Mantê-lo sob controle
é parte da disciplina:

- **Retenção explícita** por log group (`01`) — não deixar log "eterno" por default.
- **Métrica custom com parcimônia** — cada métrica custom em CloudWatch é cobrada; alto
  cardinality (por pod efêmero) explode custo.
- **S3 para longo prazo** em vez de CloudWatch Logs — barato para o que é auditoria, não busca
  diária.

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **[COST02-BP05 — Implement cost controls](https://docs.aws.amazon.com/wellarchitected/latest/cost-optimization-pillar/cost_govern_usage_controls.html)** | Budgets por conta/tag pegam desvio antes da fatura |
| **[COST05-BP01 — Identify organization requirements for cost](https://docs.aws.amazon.com/wellarchitected/latest/cost-optimization-pillar/cost_select_service_requirements.html)** | Anomaly Detection sobre padrão histórico |
| **COST** custo como sinal correlacionável | cruzar custo × NAT metrics × Flow Logs aponta a causa |
| **OPS** custo do observability sob controle | retenção explícita; métrica custom parcimoniosa |

## Próximo

→ [`05-crossplane-map.md`](05-crossplane-map.md): o que de observabilidade é provisionável e o
que é habilitação de conta.
