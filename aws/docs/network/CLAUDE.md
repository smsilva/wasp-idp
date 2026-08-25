# CLAUDE.md — `network/` (Domínio: Rede Hub-and-Spoke)

> Índice do domínio de **rede** — a fundação da arquitetura de referência. Ordem de leitura
> = ordem dos arquivos. Corpo genérico (placeholders `<...>`).

## O que este domínio entrega

Sair de uma **conta vazia** e montar a espinha dorsal de rede: um **Hub** (Connectivity
Account) com Transit Gateway e VPNs de acesso, e **spokes** (VPCs de projeto, cada cluster
uma spoke) isoladas e roteadas via TGW. Tudo componível via Crossplane e justificado contra
o Well-Architected Framework.

## Tópicos

| # | Arquivo | Assunto | Pilar WAF principal |
|---|---|---|---|
| 0 | [`00-topologia.md`](00-topologia.md) | Visão geral hub-and-spoke; por que TGW e não mesh ([REL02-BP04 — Prefer hub-and-spoke topologies over many-to-many mesh](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_prefer_hub_and_spoke.html)); contas e spokes; distinção cell-based (raio de impacto) vs. hub-and-spoke (conectividade) | Reliability |
| 1 | [`01-enderecamento-cidr.md`](01-enderecamento-cidr.md) | Plano de endereçamento IP: supernet, /16 por spoke, zero sobreposição | Reliability |
| 2 | [`02-vpc-subnets.md`](02-vpc-subnets.md) | Estrutura de VPC e subnets (pública/privada por AZ); IGW/NAT; tags EKS | Reliability |
| 3 | [`03-transit-gateway-isolamento.md`](03-transit-gateway-isolamento.md) | TGW, RAM cross-account, route table por tenant, isolamento inter-spoke | Security |
| 4 | [`04-vpn-acesso.md`](04-vpn-acesso.md) | VPN site-to-site e client; BGP/ECMP; PSK; fecha sempre no Hub | Security |
| 5 | [`05-dns.md`](05-dns.md) | Zonas Route53 por spoke, delegação, resolução cross-account | Operational Excellence |
| 6 | [`06-seguranca-rede.md`](06-seguranca-rede.md) | Security Groups, NACLs, VPC Flow Logs, endpoints privados | Security |
| 7 | [`07-mapa-crossplane.md`](07-mapa-crossplane.md) | Como cada peça vira XRD/Composition; estado atual vs alvo; gap do CIDR e migração | — |

## Sequência de construção (conta vazia → rede pronta)

```text
① Hub account criada, vazia
② Hub: VPC de trânsito (opcional) + Transit Gateway + route tables
③ Hub: RAM share do TGW com a Organization
④ Hub: VPN Gateway / Customer Gateways + VPN Connections (acesso)
⑤ Por projeto: nova account
⑥ Por cluster (spoke): VPC + subnets + attachment ao TGW + route table dedicada
⑦ Rotas e propagações: spoke ↔ hub ↔ VPN
```

Detalhe de cada passo nos tópicos acima. O mapeamento para Crossplane (o que já roda hoje
no PoC vs. o alvo multi-account) está no tópico 7.

## Estado atual vs. alvo (resumo)

- **Hoje no PoC:** uma `Network` XR (single-account, CIDR `172.16.0.0/16` fixo, 4 subnets)
  provisiona a VPC que hospeda o EKS. Não há Hub, TGW nem VPN. Ver `../../eks/resources/network/`.
- **Alvo desta referência:** Hub-and-spoke multi-account com TGW, VPN e isolamento por
  tenant — a `Network` do PoC vira uma **spoke** desse desenho maior.
- **Gap crítico já mapeado:** o CIDR `172.16.0.0/16` hardcoded é incompatível com
  hub-and-spoke (colide entre VPCs). Parametrização e alinhamento com supernet: tópicos 1 e 7.