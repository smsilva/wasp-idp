# 01 — Addressing and CIDR

**Pilar WAF principal:** Reliability ([REL02-BP01 — Use highly available network connectivity for your workload public endpoints](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_ha_conn_users.html) / [REL02-BP02 — Provision redundant connectivity between private networks in the cloud and on-premises environments](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_ha_conn_private_networks.html)).

## Por que isto vem antes de tudo

Em hub-and-spoke, **todo tráfego cruza o TGW por roteamento de CIDR**. Se dois spokes têm
CIDRs sobrepostos, o TGW não consegue distinguir os destinos — a rota é ambígua e o desenho
quebra. Endereçamento é a **primeira decisão irreversível**: mudar CIDR de uma VPC exige
recriá-la. Planeje com folga antes do primeiro `apply`.

## Regras do plano de endereçamento

1. **Uma supernet única** reservada para toda a presença AWS (ex.: `<supernet>` = um `/14`
   ou `/12`). Nada fora dela.
2. **Um bloco fixo por spoke**, sem sobreposição — por convenção, um `/16` por VPC (folga
   para subnets por AZ e crescimento).
3. **Blocos reservados não-alocáveis**: o primeiro bloco costuma ser reservado para a conta
   raiz/Org (conector de SSO/AD etc.) — spokes começam a partir do segundo.
4. **Espaço do peer externo** (Azure, on-prem) não pode colidir com a supernet AWS — o BGP
   anuncia os dois lados; sobreposição = blackhole.
5. **Documente a alocação** num único lugar (tabela de CIDR) — é o registro de verdade de
   quem tem qual bloco.

## Estrutura recomendada de um /16 de spoke

Dentro de cada VPC `<spoke-cidr>` = `<n>.<m>.0.0/16`, subnets `/24` por papel × AZ:

| Subnet | CIDR (exemplo) | Uso |
|---|---|---|
| public-AZa | `<n>.<m>.1.0/24` | NAT, load balancers públicos |
| public-AZb | `<n>.<m>.2.0/24` | idem, 2ª AZ |
| private-AZa | `<n>.<m>.3.0/24` | nós do cluster, workloads |
| private-AZb | `<n>.<m>.4.0/24` | idem, 2ª AZ |

Sobra do `/16` (`.5.0/24` em diante) fica reservada para crescimento (mais AZs, subnets de
banco, subnets de endpoints). Um `/16` por spoke é generoso de propósito — o custo de
"desperdiçar" espaço privado é zero; o custo de re-endereçar é altíssimo.

## Tabela de alocação (modelo a preencher)

| Bloco | Dono | Ambiente | Região | Observação |
|---|---|---|---|---|
| `<supernet>.0.0/24` | Org / conta raiz | — | — | **Reservado** — não alocar a spoke |
| `<spoke-1-cidr>` | Projeto A / cluster blue | dev | us-east-1 | primeiro spoke |
| `<spoke-2-cidr>` | Projeto B / cluster green | dev | us-east-1 | |
| `<hub-cidr>` | Hub / Connectivity | — | us-east-1 | VNet/VPC de trânsito, se houver |

## Plano de endereçamento decidido (2026-08-18)

- **Supernet AWS:** `10.0.0.0/12` (`10.0.0.0`–`10.15.255.255`).
- **Alocação:** um `/16` por spoke; `spec.vpcCidrSecondOctet` (N) escolhe o bloco →
  `10.<N>.0.0/16`, subnets `10.<N>.{1,2,3,4}.0/24`.
- **`10.0.0.0/16` (N=0) reservado** para a Org/raiz — spokes usam N=1..15.
- **Primeiro spoke:** N=1 → `10.1.0.0/16` (claim `examples/current/01-network.yaml`).

| Bloco | Dono | Observação |
|---|---|---|
| `10.0.0.0/16` | Org / raiz | **Reservado** — não alocar a spoke |
| `10.1.0.0/16` | 1º spoke (PoC) | `vpcCidrSecondOctet: 1` |
| `10.2.0.0/16` … `10.15.0.0/16` | próximos spokes | um N por spoke |

## ✅ Gap do CIDR hardcoded — RESOLVIDO

A `Network` XR **hardcodava `172.16.0.0/16`** (fora da supernet + fixo → todo spoke
idêntico → colisão, impossível attachar 2 ao mesmo TGW). **Resolvido em 2026-08-18:**
CIDR parametrizado via `spec.vpcCidrSecondOctet` na supernet `10.0.0.0/12`, subnets
derivadas por string-format (`%v`) em `function-patch-and-transform` — sem KCL. Validado
por `crossplane render` offline. Detalhe do "como" e o gotcha `%d`→`%v` em
[`07-crossplane-map.md`](07-crossplane-map.md).

> **Spokes de tamanho != `/16`** (ex.: `/20`) exigiriam cálculo de IP, não string-format →
> extensão futura via `function-kcl`. Hoje só `/16` alinhado à supernet.

## ⚠️ Teto do plano: 15 blocos, e região multiplica

O plano acima dá **15 blocos alocáveis** (N=1..15). Suficiente enquanto se conta *projetos*;
insuficiente assim que se conta **spoke × região**, porque cada conta que opera em duas regiões
instancia **duas** VPCs e consome **dois** blocos.

| Cenário | Spokes | Blocos |
|---|---|---|
| 1 hub + 1 control plane + 3 projetos, 1 região | 5 | 5 / 15 |
| o mesmo, 2 regiões | 10 | 10 / 15 |
| 10 tenants dedicados, 1 região | 10 | 10 / 15 |
| 10 tenants dedicados, 2 regiões | 20 | **estourou** |

O erro de dimensionamento é **contar contas e esquecer regiões**. Nenhuma correção é urgente hoje
(o consumo real é 1 bloco), mas a escolha precisa ser feita **antes** do spoke que cruzar o teto —
CIDR é a única decisão irreversível deste domínio.

### Decisão em aberto: como levantar o teto

| Caminho | Custo | Quando é o certo |
|---|---|---|
| **Ampliar a supernet** (`/12` → `/10`, `/8`) | Migração se houver spoke; um `/8` come todo o espaço privado classe A e colide com peer externo futuro | Só se **todas** as spokes precisarem de rota central |
| **CIDR repetido para spoke isolada** | Zero — é reinterpretação, não mudança | Se spoke de tenant não participa do roteamento central. Unicidade só é exigida entre VPCs que se falam |
| **VPC IPAM** com pools por região/tier | Trabalho novo; substitui o octeto calculado | Alocação em escala com múltiplas regiões e tiers |
| **Alocação bidimensional** (`/20` por spoke dentro do bloco do tier) | Exige cálculo de IP → `function-kcl` | Muitas spokes pequenas por região |

A escolha depende de uma pergunta ainda aberta: **spoke de tenant precisa de rota privada para o
hub, ou só é alcançada pela API da AWS e pelo endpoint do cluster?** Análise em
[`../tenancy/03-cidr.md`](../tenancy/03-cidr.md).

## Well-Architected — porquê

| Best practice | Como o plano atende |
|---|---|
| **[REL02-BP01 — Use highly available network connectivity for your workload public endpoints](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_ha_conn_users.html)** | `/24` por AZ, mínimo 2 AZs por spoke |
| **[REL02-BP02 — Provision redundant connectivity between private networks in the cloud and on-premises environments](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_ha_conn_private_networks.html)** | supernet única + `/16` fixo por spoke + tabela de alocação |
| **[REL02-BP04 — Prefer hub-and-spoke topologies over many-to-many mesh](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_prefer_hub_and_spoke.html)** | endereçamento não-sobreposto é pré-requisito para o TGW rotear |

## Próximo

→ [`02-vpc-subnets.md`](02-vpc-subnets.md): como o `/16` do spoke vira VPC + subnets +
IGW/NAT com as tags que o EKS exige.