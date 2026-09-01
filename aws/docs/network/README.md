# `network/` — Domain: Hub-and-Spoke Network

Índice de leitura. Convenções e regras ficam em [`CLAUDE.md`](CLAUDE.md).

## O que este domínio entrega

Sair de uma **conta vazia** e montar a espinha dorsal de rede: um **Hub** (Connectivity
Account) com Transit Gateway e VPNs de acesso, e **spokes** (VPCs de projeto, cada cluster
uma spoke) isoladas e roteadas via TGW. Tudo componível via Crossplane e justificado contra
o Well-Architected Framework.

## Tópicos

| # | Arquivo | Assunto | Pilar WAF principal |
|---|---|---|---|
| 0 | [`00-topology.md`](00-topology.md) | Visão geral hub-and-spoke; por que TGW e não mesh ([REL02-BP04 — Prefer hub-and-spoke topologies over many-to-many mesh](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_prefer_hub_and_spoke.html)); contas e spokes; distinção cell-based (raio de impacto) vs. hub-and-spoke (conectividade) | Reliability |
| 1 | [`01-cidr-addressing.md`](01-cidr-addressing.md) | Plano de endereçamento IP: supernet, /16 por spoke, zero sobreposição | Reliability |
| 2 | [`02-vpc-subnets.md`](02-vpc-subnets.md) | Estrutura de VPC e subnets (pública/privada por AZ); IGW/NAT; tags EKS | Reliability |
| 3 | [`03-transit-gateway-isolation.md`](03-transit-gateway-isolation.md) | TGW, RAM cross-account, route table por tenant, isolamento inter-spoke | Security |
| 4 | [`04-vpn-access.md`](04-vpn-access.md) | VPN site-to-site e client; BGP/ECMP; PSK; fecha sempre no Hub | Security |
| 5 | [`05-dns.md`](05-dns.md) | Zonas Route53 por spoke, delegação, resolução cross-account | Operational Excellence |
| 6 | [`06-security.md`](06-security.md) | Security Groups, NACLs, VPC Flow Logs, endpoints privados | Security |
| 7 | [`07-crossplane-map.md`](07-crossplane-map.md) | Como cada peça vira XRD/Composition; estado atual vs alvo; gap do CIDR e migração | — |
| 8 | [`08-ipam.md`](08-ipam.md) | IPAM hierárquico (escopo → pool top-level → regional → finalidade); tempos medidos de criação/destruição, custo por IP ativo, e o defeito real encontrado (o pool entregou CIDR já em uso). **Adoção adiada — [ADR 0015](../../../docs/adr/0015-defer-ipam-adoption.md); desenho aplicado e destruído duas vezes numa conta real** | Reliability |
