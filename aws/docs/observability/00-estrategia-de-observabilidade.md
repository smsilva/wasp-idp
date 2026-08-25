# 00 — Estratégia de Observabilidade

**Pilar WAF principal:** Operational Excellence (operar com base em sinais, não em suposição).

## Os três sinais

Observabilidade se apoia em três tipos de sinal, que respondem perguntas diferentes:

| Sinal | Responde | Exemplo nesta arquitetura |
|---|---|---|
| **Logs** | "o que aconteceu, exatamente?" | control plane EKS, VPC Flow Logs, CloudTrail, DNS query |
| **Métricas** | "como está, em números, ao longo do tempo?" | CPU/memória de node, tunnel state da VPN, bytes no NAT |
| **Traces** | "por onde passou uma requisição?" | tracing distribuído entre serviços (alvo, não baseline) |

Logs e métricas são o **baseline** desta referência; traces são alvo (entram quando houver
malha de serviços com latência a investigar). A regra: **ligar os dois primeiros por padrão**,
não esperar um incidente para descobrir que não havia dado.

## Observabilidade é transversal — os sinais já existem, espalhados

O erro é tratar observabilidade como um domínio isolado que "faz tudo de novo". Na verdade,
cada domínio **já produz** seus sinais; este domínio os **consolida**:

```text
../network/06   → VPC Flow Logs (o que trafegou)          ┐
../security/06  → CloudTrail (quem chamou qual API)        │
../dns/05       → DNS query logging (o que foi resolvido)  ├─►  consolidados aqui
../accounts/05  → Budgets (custo por conta)                │    numa estratégia coerente
../compute/     → control plane + Container Insights        │    (não reinventados)
../network/03-04→ TGW / VPN tunnel state                    ┘
```

O trabalho deste domínio é: **destino comum**, **retenção coerente**, **correlação** e
**alertas** — sobretudo os de conectividade (`03`), que nenhum domínio isolado enxerga porque
cruzam Hub e spoke.

## Centralização — para onde os sinais vão

Num multi-account, sinais espalhados por conta são inúteis na hora do incidente. O alvo é
**centralizar**:

- **Conta de observabilidade** (ou a de gerência/segurança) recebe logs e métricas das contas
  de projeto, via cross-account (CloudWatch cross-account observability, ou log destinations).
- **Coerente com o perímetro** (`../security/`): centralizar leitura via role cross-account
  escopada (`ReadOnlyAccess`/observabilidade), não copiar credencial.
- **CloudTrail** já é organization-wide e protegido por SCP (`../security/06`) — o modelo a
  seguir para os demais sinais.

No PoC (conta única) a centralização ainda não se aplica; é mapa para quando `../accounts/`
separar contas.

## Push vs. pull, CloudWatch vs. Prometheus

Duas escolhas de arquitetura, decididas em `02`:

- **CloudWatch** (nativo AWS) — métricas de serviços AWS (TGW, VPN, NAT, ELB) vêm de graça
  aqui; Container Insights leva node/pod para cá também.
- **Prometheus/Grafana** (ou Amazon Managed Prometheus/Grafana) — padrão Kubernetes, melhor
  para métrica de aplicação e dashboards ricos.

Não é ou-ou: métrica de **infra AWS** tende a CloudWatch (é onde nasce); métrica de
**aplicação** tende a Prometheus. O apêndice registra o que o PoC usa hoje.

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **[OPS08-BP01 — Analyze workload metrics](https://docs.aws.amazon.com/wellarchitected/latest/operational-excellence-pillar/ops_workload_observability_analyze_workload_metrics.html)** | logs + métricas ligados por padrão em cada spoke |
| **[OPS08-BP04 — Create actionable alerts](https://docs.aws.amazon.com/wellarchitected/latest/operational-excellence-pillar/ops_workload_observability_create_alerts.html)** | destino comum permite cruzar Flow Logs × CloudTrail × métricas |
| **[OPS04 — Implement observability](https://docs.aws.amazon.com/wellarchitected/latest/operational-excellence-pillar/implement-observability.html)** | cada domínio contribui seu sinal; este consolida |
| **SEC** leitura centralizada segura | role cross-account escopada, não credencial copiada |

## Próximo

→ [`01-logs.md`](01-logs.md): as fontes de log, retenção e destino.
