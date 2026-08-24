# 03 — Transit Gateway e Isolamento

**Pilar WAF principal:** Security (SEC05 — isolamento de rede) + Reliability (REL02-BP04).

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
| **SEC05-BP01** múltiplas camadas | conta + TGW route table + VPC route table + SG/NACL |
| **SEC05-BP02** todas as camadas controlam tráfego | isolamento por `tgw-rt-<spoke>`, não só por SG |
| **REL02-BP04** hub-and-spoke | TGW central com roteamento explícito |
| **COST** route tables grátis | isolamento por route table não adiciona custo |

## Próximo

→ [`04-vpn-acesso.md`](04-vpn-acesso.md): como VPNs de acesso fecham no Hub com BGP/ECMP.