# 03 — CIDR e Tenancy (onde o plano de endereçamento estoura)

**Pilar WAF principal:** Reliability
([REL02 — Plan your network topology](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/plan-your-network-topology.html)).

## O plano vigente e o seu teto

O domínio de rede aloca **um `/16` por spoke** dentro da supernet `10.0.0.0/12`, escolhido por
`spec.vpcCidrSecondOctet` (N), com N=0 reservado para a Org (`../network/01-enderecamento-cidr.md`).
Isso dá **15 blocos alocáveis**: N=1..15.

Quinze parece confortável enquanto se conta *projetos*. Deixa de ser quando se conta
**tenant × região**:

| Cenário | Spokes | Blocos consumidos |
|---|---|---|
| 3 projetos internos, 1 região | 3 | 3 / 15 |
| 10 tenants siloados, 1 região | 10 | 10 / 15 |
| 10 tenants siloados, 2 regiões | 20 | **20 / 15 — estourou** |
| 1 hub por região + control plane por região (2 regiões) | 4 | 4 / 15 antes de qualquer tenant |

**Região multiplica, não soma.** O erro de dimensionamento é contar contas (ou tenants) e
esquecer que cada um instancia uma VPC por região onde opera.

## Por que ampliar a supernet é a saída ruim

Trocar `/12` por `/8` daria 255 blocos e parece resolver. Mas:

- **CIDR é a decisão irreversível** desta arquitetura — trocar exige recriar VPC. Ampliar depois
  de existir spoke é uma migração, não um ajuste de parâmetro.
- Um `/8` inteiro em `10.0.0.0/8` consome **todo** o espaço privado classe A. Qualquer peer
  externo futuro (on-prem, parceiro, aquisição) passa a colidir por construção.
- Não ataca a causa: continua tratando spoke de tenant isolado como se ela precisasse ser
  roteável para todo o resto.

## A observação que muda o problema

**CIDR único só é necessário entre VPCs que se comunicam.** A unicidade existe para o roteamento
do TGW poder distinguir destinos. Duas VPCs que nunca trocam pacote podem ter o **mesmo** bloco —
a AWS não impede, e nada quebra.

E isolamento entre tenants é justamente o **propósito** do silo. Logo:

```text
10.0.0.0/12  ← espaço ROTEÁVEL (participa do TGW, precisa ser único)
├── 10.0.0.0/16   reservado — Org
├── 10.1.0.0/16   hub / infra compartilhada
├── 10.2.0.0/16   control plane regional
└── 10.3..15.0/16 spokes que precisam de rota para o hub

<bloco-padrão-de-tenant>  ← REPETIDO em cada spoke de tenant isolado
```

Cada tenant siloado nasce com o **mesmo** bloco. O espaço roteável fica reservado para o que de
fato participa do roteamento central — e deixa de ser consumido por população de clientes.

## A premissa que sustenta isso (e precisa ser validada)

O bloco repetido só funciona se a spoke de tenant **não precisar de rota** para o hub nem para
outra spoke. Isso cai se qualquer uma destas for verdadeira:

| Requisito | Efeito |
|---|---|
| Control plane alcança a spoke **por rede** (não só via API AWS) | Precisa de rota → CIDR único obrigatório |
| Observabilidade/backup por conexão privada centralizada | idem |
| VPN de operador entra no hub e precisa chegar ao tenant | idem |
| Serviço compartilhado (registry interno, resolver) consumido por rota privada | idem |

**Como validar:** o Crossplane do control plane fala com a AWS pela **API pública** (endpoints
STS/EKS/EC2), e com o EKS gerenciado pelo **endpoint do cluster**. Nenhum dos dois exige rota
TGW. Se o padrão for esse — API pública para provisionar, endpoint público/allowlist para o
kubeconfig — a premissa se sustenta. Se a decisão for control plane alcançando spokes por rede
privada, o bloco repetido está descartado.

Alternativas quando a premissa cai:

1. **PrivateLink por serviço** em vez de rota ampla — mantém o bloco repetido, expõe só o
   endpoint necessário. PrivateLink funciona com CIDR sobreposto.
2. **VPC IPAM** com pools por região e por tier, em vez de octeto calculado em patch — é a
   ferramenta certa para alocação em escala, e `../../../decisions.md` §7 já registra "IPAM cedo"
   como armadilha conhecida.
3. **Alocação bidimensional** (N por tier/região, `/20` por tenant dentro do bloco do tier) —
   exige cálculo de IP, o que hoje demandaria `function-kcl`
   (`../network/01-enderecamento-cidr.md`).

## Decisão em aberto

Nada aqui altera o plano vigente. O que está registrado é que **o plano vigente tem teto de 15**
e que a escolha entre os três caminhos depende de uma pergunta ainda não respondida:

> O control plane precisa alcançar a spoke de tenant **por rede privada**, ou só pela API da AWS
> e pelo endpoint do cluster?

Enquanto isso não é decidido, não vale ampliar supernet nem migrar para IPAM — as duas são caras
e uma delas seria desperdício. Ver a decisão registrada em
[`CLAUDE.md`](CLAUDE.md) e em `../network/01-enderecamento-cidr.md`.

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **[REL02 — Plan your network topology](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/plan-your-network-topology.html)** | O teto do plano de endereçamento é calculado antes de ser atingido, não descoberto no tenant 16 |
| **[REL02-BP04 — Prefer hub-and-spoke topologies over many-to-many mesh](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_prefer_hub_and_spoke.html)** | Só o que participa do hub consome espaço roteável — o hub não vira registro de toda VPC existente |
| **COST** — espaço privado não é recurso escasso, re-endereçar é caro | Reservar espaço roteável para quem roteia evita a migração de CIDR, que é o cenário caro |

## Próximo

→ Volta ao índice do domínio: [`CLAUDE.md`](CLAUDE.md). Para o plano de endereçamento em si,
`../network/01-enderecamento-cidr.md`.
