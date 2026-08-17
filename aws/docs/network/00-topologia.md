# 00 — Topologia Hub-and-Spoke

**Pilar WAF principal:** Reliability (REL02 — planejamento de topologia de rede).

## O problema que a topologia resolve

Quando cada VPC precisa falar com as outras (e com VPNs externas), há dois caminhos:

- **Mesh (peering ponto-a-ponto):** N VPCs → até N×(N-1)/2 peerings. Cada VPN externa
  replicada em cada VPC. Não escala; roteamento vira um emaranhado; inserir um firewall
  central é impossível sem refactor.
- **Hub-and-spoke (via Transit Gateway):** N VPCs → N attachments a **um** hub. Roteamento
  central, um ponto para observar, um lugar para inserir firewall/VPN. Escala linearmente.

**Decisão:** hub-and-spoke via **AWS Transit Gateway**. Alinhado ao Well-Architected
**REL02-BP04** ("Prefer hub-and-spoke topologies over many-to-many mesh") e ao próprio
design consolidado da organização (ver `<hub-repo>/.../2026-05-26-hub-spoke-design.md`).

## Visão geral

```text
                        ┌──────────────────────────────┐
                        │   Hub / Connectivity Account    │
                        │                                 │
   VPN de acesso  ◄────►│   VPN GW / CGW  ──┐            │
   (site-to-site,       │                    │            │
    client, on-prem)    │              Transit Gateway    │
                        │                  │   │   │      │
                        │      tgw-rt-hub ─┘   │   │      │
                        └─────────────────────┼──┼─────┘
                              RAM share (Org)   │   │
                    ┌───────────────┬─────────┘  └──────────┐
                    ▼                ▼                          ▼
        ┌────────────────┐ ┌────────────────┐    ┌────────────────┐
        │ Project A acct   │ │ Project B acct  │    │ Project N acct   │
        │  VPC spoke       │ │  VPC spoke      │    │  VPC spoke       │
        │  (cluster =      │ │  (cluster =     │    │  (cluster =      │
        │   1 spoke)       │ │   1 spoke)      │    │   1 spoke)       │
        │  tgw-rt-A        │ │  tgw-rt-B       │    │  tgw-rt-N        │
        └────────────────┘ └────────────────┘    └────────────────┘
```

## As três camadas de contas

| Camada | Conta | Contém | Ciclo de vida |
|---|---|---|---|
| **Hub** | Connectivity Account (dedicada) | Transit Gateway, `tgw-rt-hub`, VPN GW/CGW, VPN Connections, RAM shares | Estável — provisionado 1× por região |
| **Projeto** | Uma account por projeto | Recursos do projeto; pode ter 1+ spokes | Por projeto |
| **Spoke** | Dentro da account de projeto | VPC + subnets + attachment ao TGW + `tgw-rt-<spoke>` | Por cluster (cada cluster = 1 spoke) |

**Por que account por projeto?** Isolamento de blast radius, billing por projeto, e cotas
AWS que são por-conta (VPCs, EIPs) deixam de ser limite arquitetural global. Todas as
contas vivem na mesma **AWS Organization** → o RAM share do TGW é auto-aceito, sem
aprovação manual por attachment.

**Por que cada cluster é uma spoke?** Um cluster = uma VPC = um attachment = uma route
table dedicada. Isso dá isolamento de rede por cluster e permite políticas de roteamento
independentes (um cluster de dev não enxerga um de prod, mesmo no mesmo TGW).

## Fluxo de dados (resumo)

```text
Externo → Spoke:   VPN → tgw-rt-hub → (rota: CIDR do spoke) → spoke attachment → VPC
Spoke → Externo:   VPC → spoke attachment → tgw-rt-<spoke> → (rota: CIDR remoto) → VPN
Spoke ↔ Spoke:     só se explicitamente roteado via Hub — default é NÃO alcançar
```

O isolamento inter-spoke não é acidental: cada `tgw-rt-<spoke>` contém **apenas** as rotas
daquele spoke. Detalhe em [`03-transit-gateway-isolamento.md`](03-transit-gateway-isolamento.md).

## Well-Architected — porquê

| Best practice | Como a topologia atende |
|---|---|
| **REL02-BP04** hub-and-spoke > mesh | TGW central; N attachments, não N×M peerings |
| **REL02-BP01** conectividade privada altamente disponível | TGW é regional e multi-AZ por design; VPN com 2 túneis + BGP |
| **SEC05-BP01** camadas de rede | Contas isolam; route tables por spoke isolam; SG/NACL na VPC (tópico 6) |
| **COST** | Route tables no TGW não têm custo; account por projeto habilita billing granular |

## Limitações conhecidas nesta fase

- **Failover multi-região** (Hub de uma região assume outra): fora de escopo inicial. A
  redundância aqui é intra-região (multi-AZ + 2 túneis VPN + BGP).
- **Template de criação de account**: enquanto não houver automação de account, o desenho
  opera em **conta única** (hub e spoke na mesma conta) — o código detecta e suprime RAM
  share / attachment accepter. Não é a topologia final, é o degrau de bootstrap.

## Próximo

→ [`01-enderecamento-cidr.md`](01-enderecamento-cidr.md): sem um plano de CIDR sem
sobreposição, o hub-and-spoke não roteia. É o pré-requisito de tudo.