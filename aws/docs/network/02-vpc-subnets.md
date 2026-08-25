# 02 — VPC and Subnets (the spoke)

**Pilar WAF principal:** Reliability ([REL02-BP01 — Use highly available network connectivity for your workload public endpoints](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_ha_conn_users.html)) + Security ([SEC05 — Protecting networks](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/protecting-networks.html)).

## O que é um spoke, concretamente

Um spoke = **uma VPC** dentro de uma account de projeto, dividida em subnets pública/privada
por AZ, com saída controlada (IGW para público, NAT para privado) e um attachment ao TGW do
Hub (tópico 3). No caso desta referência, **cada cluster EKS é hospedado por um spoke**.

## Anatomia da VPC do spoke

```text
VPC <spoke-cidr> (/16)   enableDnsSupport + enableDnsHostnames
├── public-AZa  (/24)  ── map public IP ── ┐
├── public-AZb  (/24)  ── map public IP ── ┤── RouteTable public ── 0.0.0.0/0 → IGW
├── private-AZa (/24) ─────────────────────┐
├── private-AZb (/24) ─────────────────────┤── RouteTable private ── 0.0.0.0/0 → NAT
│                                           │                        <remote-cidr> → TGW
├── InternetGateway (IGW)
├── EIP + NATGateway (na public-AZa)
└── (attachment ao TGW — ver tópico 3)
```

## Componentes e o porquê de cada um

| Componente | Quantos | Porquê |
|---|---|---|
| **VPC** | 1 | O envelope do spoke; DNS support/hostnames ligados (exigência do EKS e do Route53 privado) |
| **Subnet pública** | 1 por AZ (≥2) | Load balancers internet-facing, NAT. `map_public_ip_on_launch=true` |
| **Subnet privada** | 1 por AZ (≥2) | Nós do cluster e workloads — sem IP público, saída via NAT |
| **Internet Gateway** | 1 | Saída/entrada pública; só existe se há subnet pública |
| **NAT Gateway + EIP** | 1 (ou 1 por AZ p/ HA) | Saída privada para internet (pull de imagens, APIs). 1 por AZ elimina ponto único |
| **Route Table pública** | 1 | `0.0.0.0/0 → IGW`; associada às subnets públicas |
| **Route Table privada** | 1 (ou 1 por AZ) | `0.0.0.0/0 → NAT` + rotas de CIDR remoto `→ TGW`; associada às privadas |

**NAT: 1 vs. 1-por-AZ.** Um NAT único é mais barato mas é ponto único de falha e cobra
tráfego cross-AZ. Para produção, **1 NAT por AZ** ([REL10 — Use fault isolation to protect your workload](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/use-fault-isolation-to-protect-your-workload.html)). Para
dev/PoC, 1 NAT é aceitável e economiza. Deixe isto **parametrizável**, não fixo.

## Tags obrigatórias para o EKS

O EKS/load balancer controller descobre subnets por tag — sem elas, o provisionamento de
ELB/ALB falha:

| Tag | Valor | Em quais subnets |
|---|---|---|
| `kubernetes.io/role/elb` | `1` | públicas (ELB internet-facing) |
| `kubernetes.io/role/internal-elb` | `1` | privadas (ELB interno) |
| `kubernetes.io/cluster/<cluster-name>` | `shared` / `owned` | todas as do cluster (quando aplicável) |

## Contrato de saída do spoke (composable design)

Um spoke bem-feito **publica o que compõe**, para que a camada de cima (o Cluster) consuma
sem inspecionar recurso por recurso:

- **`status.vpcId`** e **`status.subnetIds`** (por papel) — para diagnóstico e para o Cluster
  referenciar as subnets.
- **Labels/tags determinísticas** nas subnets (papel, tier public/private) — para seleção.

Esse é exatamente o contrato que a `Network` XR do PoC já implementa (publica `vpcId` e
`subnetIds`, taggeia subnets por papel). Detalhe do mapeamento em
[`07-crossplane-map.md`](07-crossplane-map.md).

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **[REL02-BP01 — Use highly available network connectivity for your workload public endpoints](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_ha_conn_users.html)** | mínimo 2 AZs, público+privado em cada |
| **[REL10-BP01 — Deploy the workload to multiple locations](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_fault_isolation_multiaz_region_system.html)** | NAT por AZ (produção); route table privada por AZ |
| **[SEC05-BP01 — Create network layers](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_network_protection_create_layers.html)** | workloads em subnet privada sem IP público; público só para ingress |
| **[SEC05-BP02 — Control traffic flow within your network layers](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_network_protection_layered.html)** | saída privada forçada via NAT; entrada só via LB público |

## Próximo

→ [`03-transit-gateway-isolation.md`](03-transit-gateway-isolation.md): como o spoke se
conecta ao Hub e por que um spoke não enxerga o outro.