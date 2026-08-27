# CLAUDE.md — `network/` (Domain: Hub-and-Spoke Network)

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
| 0 | [`00-topology.md`](00-topology.md) | Visão geral hub-and-spoke; por que TGW e não mesh ([REL02-BP04 — Prefer hub-and-spoke topologies over many-to-many mesh](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_prefer_hub_and_spoke.html)); contas e spokes; distinção cell-based (raio de impacto) vs. hub-and-spoke (conectividade) | Reliability |
| 1 | [`01-cidr-addressing.md`](01-cidr-addressing.md) | Plano de endereçamento IP: supernet, /16 por spoke, zero sobreposição | Reliability |
| 2 | [`02-vpc-subnets.md`](02-vpc-subnets.md) | Estrutura de VPC e subnets (pública/privada por AZ); IGW/NAT; tags EKS | Reliability |
| 3 | [`03-transit-gateway-isolation.md`](03-transit-gateway-isolation.md) | TGW, RAM cross-account, route table por tenant, isolamento inter-spoke | Security |
| 4 | [`04-vpn-access.md`](04-vpn-access.md) | VPN site-to-site e client; BGP/ECMP; PSK; fecha sempre no Hub | Security |
| 5 | [`05-dns.md`](05-dns.md) | Zonas Route53 por spoke, delegação, resolução cross-account | Operational Excellence |
| 6 | [`06-security.md`](06-security.md) | Security Groups, NACLs, VPC Flow Logs, endpoints privados | Security |
| 7 | [`07-crossplane-map.md`](07-crossplane-map.md) | Como cada peça vira XRD/Composition; estado atual vs alvo; gap do CIDR e migração | — |
| 8 | [`08-ipam.md`](08-ipam.md) | IPAM hierárquico (escopo → pool top-level → regional → finalidade); por que a tabela manual é anti-pattern de REL02-BP05; gatilhos de adoção. **Desenho, nada implementado** | Reliability |

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

## Armadilha: route table de tenant só isola se o attachment for por tenant

O isolamento em dois níveis do tópico 3 (`tgw-rt-<spoke>` + rotas na VPC) pressupõe **um attachment
de VPN por cliente**. Com um attachment **agregado** — um concentrador único a montante, servindo
vários clientes pelos mesmos túneis — todos os CIDRs de cliente chegam pelo mesmo attachment e são
aprendidos por BGP na mesma route table. Consequência:

- **saída** (spoke → cliente) continua isolada: a RT privada da spoke só ganha rota para os CIDRs
  remotos declarados;
- **entrada** (cliente → spoke) **não** fica isolada no TGW, porque o CIDR de toda spoke é
  propagado na `tgw-rt-hub` para o tráfego de retorno funcionar. Sobra só security group/NACL
  dentro da spoke — uma camada, e a mais interna.

Isso rebaixa `SEC05-BP01`/`BP02` (camadas de rede, controle de fluxo em todas elas) a uma camada
nessa direção. Aceitável como decisão registrada; inaceitável como efeito colateral. Saídas: VPN por
cliente, VPC de inspeção com Network Firewall no caminho, ou PrivateLink em vez de rota.

**Neste repo a decisão é VPN por cliente**, justamente para manter as duas direções isoladas por
topologia.

## Duas coisas que o TGW não faz

- **TGW entrega roteamento IP, não resolução de nome.** O endpoint privado da API do EKS resolve por
  uma private hosted zone associada à VPC do cluster; de outra VPC o hostname não resolve mesmo com
  rota. Saídas: associar a zona à VPC de origem, ou Route 53 Resolver inbound endpoint.
- **Route table por spoke não isola cliente de cliente.** Se o attachment de VPN de um cliente
  associar à `tgw-rt-hub` — que tem todas as spokes propagadas — ele alcança todas. É preciso
  **route table por cliente** também, contendo só o CIDR da spoke dele. Isolamento é simétrico e
  aditivo: acrescentar cliente é acrescentar rota nos dois lados.
