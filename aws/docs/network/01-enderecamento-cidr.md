# 01 — Endereçamento e CIDR

**Pilar WAF principal:** Reliability (REL02-BP01/BP02 — planejamento de sub-rede e
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

## ⚠️ Gap conhecido no código atual do PoC

A `Network` XR do PoC hoje **hardcoda `172.16.0.0/16`** na Composition
(`../../eks/resources/network/composition.yaml`). Dois problemas para hub-and-spoke:

1. **Range fora da supernet planejada** — se a referência adotar `10.x` (padrão da organização,
   ver apêndice), `172.16` fica órfão.
2. **Fixo → todo spoke nasceria com o mesmo CIDR** → sobreposição imediata; impossível
   attachar dois ao mesmo TGW.

**Direção decidida (brainstorm):** parametrizar o CIDR no spec da `Network`
(ex.: `spec.vpcCidrSecondOctet`, formato `<base>.<N>.0.0/16`, `N` validado por pattern no
XRD; 4 subnets derivadas por string-format em patch-and-transform, sem KCL). O caminho de
migração e o "como" estão em [`07-mapa-crossplane.md`](07-mapa-crossplane.md).

## Well-Architected — porquê

| Best practice | Como o plano atende |
|---|---|
| **REL02-BP01** subnets HA | `/24` por AZ, mínimo 2 AZs por spoke |
| **REL02-BP02** sem sobreposição de IP | supernet única + `/16` fixo por spoke + tabela de alocação |
| **REL02-BP04** hub-and-spoke | endereçamento não-sobreposto é pré-requisito para o TGW rotear |

## Próximo

→ [`02-vpc-subnets.md`](02-vpc-subnets.md): como o `/16` do spoke vira VPC + subnets +
IGW/NAT com as tags que o EKS exige.