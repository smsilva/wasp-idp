# 03 — Connectivity Alerts

**Pilar WAF principal:** Reliability ([REL02 — Plan your network topology](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/plan-your-network-topology.html); [REL06 — Monitor workload resources](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/monitor-workload-resources.html)).

## O modo de falha próprio do hub-and-spoke

Cada domínio tem alarmes óbvios (pod caindo, disco cheio). Mas o hub-and-spoke introduz um modo
de falha que **nenhum domínio isolado enxerga**, porque cruza Hub e spoke: a **conectividade**.
Um túnel VPN que cai, um attachment do TGW que vira blackhole, um NAT que satura — nada disso
aparece num log de app; a app só vê "timeout". Este tópico é o que torna essas falhas
**visíveis antes** de virarem incidente.

## Os alarmes de conectividade essenciais

Contra as métricas de `02`, os alarmes que valem a pena:

| Alarme | Métrica / condição | Por que importa |
|---|---|---|
| **Túnel VPN down** | `TunnelState = 0` por túnel | 1 túnel caído = HA perdida (o outro segura, mas sem redundância — agir) |
| **VPN totalmente down** | ambos os túneis de uma conexão em 0 | conectividade com o peer **perdida** — acordar alguém |
| **TGW blackhole / no-route** | `PacketDropCount-Blackhole` > 0 | rota faltando em `tgw-rt-<spoke>` → tráfego caindo (config errada ou isolamento indevido) |
| **NAT saturando** | `ErrorPortAllocation` > 0 / `BytesOut` perto do teto | saída do spoke degradando (e custo subindo) |
| **NAT indisponível** | queda abrupta de `BytesOut` num spoke ativo | perda de saída à internet do spoke |

Contexto: as métricas de VPN/TGW **só existem quando a rede de conectividade existir**
(`../network/07`, Gap 2). Hoje são mapa; o NAT do spoke atual já é alarmável.

## Severidade — o que acorda alguém

Nem todo alarme é página noturna. Separar por severidade evita fadiga de alerta:

```text
CRÍTICO (acordar)   VPN inteira down; NAT indisponível; TGW dropando em massa
                    → conectividade PERDIDA, apps afetadas agora
AVISO (horário útil) 1 túnel down (HA degradada mas de pé); NAT perto do teto; blackhole pontual
                    → risco/degradação, não queda — tratar sem pânico
INFO (só registra)   flaps isolados que se recuperam sozinhos (BGP reconvergindo)
```

Regra: **HA degradada é AVISO, HA perdida é CRÍTICO.** Um túnel caído com o outro de pé não é
emergência (o BGP/ECMP — `../network/04` — já redistribuiu); os **dois** caídos é.

## Do alarme à notificação

O caminho padrão em AWS:

```text
CloudWatch Alarm (limiar sobre a métrica)
   → SNS topic (por severidade)
      → e-mail / Slack / PagerDuty / Lambda de auto-remediação
```

- **Um SNS topic por severidade** — crítico e aviso roteiam para canais diferentes.
- **Auto-remediação** onde fizer sentido (ex.: um túnel flapando dispara só registro; não há o
  que "consertar" automaticamente numa VPN — a ação é humana). Não automatizar resposta a algo
  cuja causa é externa (peer remoto).

## Correlação com os outros sinais

Um alarme de conectividade **aponta onde olhar**, não a causa. A investigação cruza (`01`):

```text
Alarme: TGW blackhole no spoke A
  → CloudTrail: alguém mudou tgw-rt-A? (../security/06)
  → VPC Flow Logs: o tráfego de A está sendo dropado? (../network/06)
  → estado do attachment/rota (../network/03)
```

O alarme é o gatilho; os logs contam a história.

## Alarmes de compute e DNS (complemento)

Além da conectividade, o baseline inclui:

- **Compute:** node `NotReady`, pod `CrashLoopBackOff` recorrente (o sintoma da race de Pod
  Identity — `../compute/02`), memória de node perto do limite.
- **DNS/cert:** falha de renovação de certificado (o desafio DNS-01 eterno — `../dns/04`),
  spike anômalo de query (via query logging — `../dns/05`).

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **[REL06-BP01 — Monitor all components for the workload](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_monitor_aws_resources_monitor_resources.html)** / **[REL06-BP02 — Define and calculate metrics](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_monitor_aws_resources_notification_aggregation.html)** | alarmes sobre tunnel/TGW/NAT antecipam perda de conectividade |
| **[REL02-BP01 — Use highly available network connectivity for your workload public endpoints](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_ha_conn_users.html)** | distinguir HA degradada (aviso) de HA perdida (crítico) |
| **[OPS10-BP01 — Use a process for event, incident, and problem management](https://docs.aws.amazon.com/wellarchitected/latest/operational-excellence-pillar/ops_event_response_event_incident_problem_process.html)** | SNS por severidade → canal certo; auto-remediação onde cabe |
| **OPS** reduzir fadiga | severidade separada; INFO para flaps auto-recuperáveis |

## Próximo

→ [`04-cost-as-signal.md`](04-cost-as-signal.md): custo também é telemetria — desvio é
alarme.
