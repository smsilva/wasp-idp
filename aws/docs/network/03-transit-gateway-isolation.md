# 03 — Transit Gateway and Isolation

**Pilar WAF principal:** Security ([SEC05 — Protecting networks](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/protecting-networks.html)) + Reliability ([REL02-BP04 — Prefer hub-and-spoke topologies over many-to-many mesh](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_prefer_hub_and_spoke.html)).

## O papel do Transit Gateway

O TGW é o **núcleo do Hub**. Vive na Connectivity Account. Tudo que precisa se comunicar
— cada VPC spoke, cada VPN externa — se **attacha** a ele. O roteamento entre attachments
é decidido por **route tables do TGW**, não pelas route tables das VPCs. Isso centraliza a
política de conectividade em um lugar auditável.

## Configuração do TGW (defaults deliberados)

| Config | Valor | Porquê |
|---|---|---|
| `defaultRouteTableAssociation` | **disable** | Nenhum attachment herda roteamento automático — cada um é associado explicitamente. Sem isso, todo spoke enxergaria todo spoke. |
| `defaultRouteTablePropagation` | **disable** | CIDRs não se propagam sozinhos entre attachments; propagação é explícita por route table. É o que torna o isolamento possível. |
| `vpnEcmpSupport` | **enable** | Distribui tráfego entre múltiplos túneis VPN ativos (ver tópico 4) |
| `dnsSupport` | **enable** | Resolução de nomes através do TGW |
| `amazonSideAsn` | `<hub-asn>` | ASN BGP do lado AWS (ex.: `64512`), consistente por região |

> **Association vs. Propagation** — os dois conceitos que definem isolamento:
> - **Association**: em qual route table o *tráfego que entra* por um attachment é avaliado.
> - **Propagation**: quais route tables *aprendem* o CIDR daquele attachment.
> Desligar ambos os defaults e configurar caso a caso é o que impede vazamento inter-spoke.

## Route tables do TGW

| Route table | Onde vive | Contém | Associada a |
|---|---|---|---|
| **`tgw-rt-hub`** | Hub | rotas para os spokes (propagadas) + CIDRs das VPNs | os attachments de **VPN** |
| **`tgw-rt-<spoke>`** | Hub (1 por spoke) | **só** o CIDR do próprio spoke + CIDRs remotos que ele pode alcançar | o attachment daquele spoke |

**Isolamento em dois níveis:**

1. **TGW route table por spoke** — `tgw-rt-<spoke>` só tem as rotas daquele tenant. Um spoke
   não aprende a rota de outro spoke porque a route table dele não a contém. Custo: zero
   (route tables do TGW não são cobradas).
2. **Route tables da VPC** — no spoke, só os CIDRs remotos explicitamente declarados apontam
   para o TGW. Saída é explícita, por spoke.

```text
Spoke A quer falar com Spoke B?
  tgw-rt-A não tem rota para o CIDR de B  →  blackhole  →  NÃO alcança.
  (Só alcança se uma rota for adicionada explicitamente — decisão consciente, via Hub.)
```

### ⚠️ O teto deste desenho são **20 route tables por TGW**, não o plano de CIDR

Route table de TGW é grátis, mas **não é ilimitada**. Do
[quotas do TGW](https://docs.aws.amazon.com/vpc/latest/tgw/transit-gateway-quotas.html)
(verificado 2026-08-27):

| Quota | Default | Ajustável |
|---|---|---|
| **Route tables por TGW** | **20** | sim (Service Quotas) |
| Attachments por TGW | 5.000 | sim |
| Rotas totais (dinâmicas + estáticas) em **todas** as route tables de um TGW | 10.000 | só via SA/TAM |
| Peering attachments por TGW | 50 | sim |
| Rotas estáticas para um mesmo prefixo apontando a um attachment | 1 | não |

**Por que 20 morde primeiro aqui.** O desenho acima gasta uma `tgw-rt-<spoke>` por spoke, e o
desenho de VPN por cliente (`04-vpn-access.md`) gasta mais uma `tgw-rt-cliente-<x>` por cliente.
São **2 por cliente** — logo ~9 clientes mais a `tgw-rt-hub` e o default está esgotado. Isso
acontece **antes** de qualquer teto do plano de endereçamento (15 blocos sob a supernet `/12`,
ver [`01-cidr-addressing.md`](01-cidr-addressing.md)).

Consequências práticas:

- **É pedido de Service Quotas, não mudança de desenho.** Ajustável, mas com lead time — não se
  descobre isso na véspera de onboardear o décimo cliente.
- **Os 10.000 de rotas totais valem para o TGW inteiro**, somando todas as tabelas. Com rota por
  spoke em cada tabela de cliente, o número cresce como produto, não como soma. É o quota mais
  rígido dos quatro (só sobe falando com SA/TAM).
- **Acima dessa faixa, o mecanismo deixa de ser route table.** É onde entra o **AWS Cloud WAN**:
  segmento é política declarativa aplicada a attachments por tag, não objeto que alguém cria e
  associa um a um. Há peering TGW ↔ Cloud WAN com policy tables, então a migração é incremental.
  A [Hybrid Networking Lens](https://docs.aws.amazon.com/wellarchitected/latest/hybrid-networking-lens/hnsec01-bp01.html)
  do Well-Architected trata os dois no mesmo best practice de segmentação.

**Não é problema hoje** (há 1 route table de spoke). É o número a ter em mente ao desenhar a
fase de provas de isolamento, que é a primeira a criar `tgw-rt-cliente-<x>`.

## Compartilhamento cross-account via AWS RAM (modelo descentralizado)

Para uma VPC de outra account attachar-se ao TGW do Hub, o TGW precisa ser compartilhado
com aquela account via **Resource Access Manager (RAM)**. Modelo adotado: **descentralizado**
— o próprio provisionamento do spoke cria o RAM share na conta `network`, com escopo limitado à
account daquele tenant.

- `ResourceShare` — `ram-share-tgw-<region>-<tenant>` na conta `network`
- `ResourceAssociation` — associa o TGW ao share
- `PrincipalAssociation` — associa o account ID do spoke ao share
- `allowExternalPrincipals=false` — só contas da mesma Organization aceitam

**Vantagens:** o Hub não precisa conhecer a lista de tenants; remover o tenant remove o
share junto (sem lixo); sem race entre onboardings simultâneos.

**Cenário de conta única (bootstrap):** quando hub e spoke estão na mesma conta, RAM share
e attachment accepter são **suprimidos** (não há cross-account a compartilhar). O código
detecta isso automaticamente. É o degrau até o template de account estar pronto.

## Attachment do spoke

```text
Na account do spoke:   TransitGatewayVPCAttachment (VPC → TGW)
Na account do Hub:      TransitGatewayVPCAttachmentAccepter (aceita, se cross-account)
                        + tgw-rt-<spoke> (associação + propagação do CIDR do spoke)
                        + rota em tgw-rt-hub para o CIDR do spoke
```

Intra-Org com auto-accept, o accepter é dispensável; cross-Org ele é obrigatório (ver
débito técnico no apêndice).

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **[SEC05-BP01 — Create network layers](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_network_protection_create_layers.html)** | conta + TGW route table + VPC route table + SG/NACL |
| **[SEC05-BP02 — Control traffic flow within your network layers](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_network_protection_layered.html)** | isolamento por `tgw-rt-<spoke>`, não só por SG |
| **[REL02-BP04 — Prefer hub-and-spoke topologies over many-to-many mesh](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_prefer_hub_and_spoke.html)** | TGW central com roteamento explícito |
| **COST** route tables grátis | isolamento por route table não adiciona custo |

## Próximo

→ [`04-vpn-access.md`](04-vpn-access.md): como VPNs de acesso fecham no Hub com BGP/ECMP.