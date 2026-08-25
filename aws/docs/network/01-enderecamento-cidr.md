# 01 — Endereçamento e CIDR

**Pilar WAF principal:** Reliability ([REL02-BP01](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_ha_conn_users.html)/BP02 — planejamento de sub-rede e
endereçamento não sobreposto).

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
[`07-mapa-crossplane.md`](07-mapa-crossplane.md).

> **Spokes de tamanho != `/16`** (ex.: `/20`) exigiriam cálculo de IP, não string-format →
> extensão futura via `function-kcl`. Hoje só `/16` alinhado à supernet.

## Well-Architected — porquê

| Best practice | Como o plano atende |
|---|---|
| **[REL02-BP01](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_ha_conn_users.html)** subnets HA | `/24` por AZ, mínimo 2 AZs por spoke |
| **[REL02-BP02](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_ha_conn_private_networks.html)** sem sobreposição de IP | supernet única + `/16` fixo por spoke + tabela de alocação |
| **[REL02-BP04](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_prefer_hub_and_spoke.html)** hub-and-spoke | endereçamento não-sobreposto é pré-requisito para o TGW rotear |

## Próximo

→ [`02-vpc-subnets.md`](02-vpc-subnets.md): como o `/16` do spoke vira VPC + subnets +
IGW/NAT com as tags que o EKS exige.