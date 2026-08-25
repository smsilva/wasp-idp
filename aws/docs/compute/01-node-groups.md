# 01 — Node Groups

**Pilar WAF principal:** Reliability (capacidade HA) + Cost Optimization (spot, sizing).

## Managed node group — o data plane gerenciado

Um **managed node group** é um conjunto de instâncias EC2 que a AWS provisiona, registra no
cluster e cicla em upgrades — você declara o *shape* (tipo, tamanho, subnets), a AWS cuida do
resto (Auto Scaling Group, AMI otimizada para EKS, drenagem em update). É o padrão desta
referência (vs. self-managed nodes ou Fargate).

- **Independente do cluster no modelo do EKS:** o `NodeGroup` (`eks.aws.upbound.io`)
  referencia o cluster (`clusterNameSelector`), não é um sub-campo dele. Um cluster pode ter
  **vários** node groups.
- **AMI e bootstrap** gerenciados pela AWS — sem user-data manual na maioria dos casos.

## Sempre nas subnets privadas

Node groups vão nas subnets **privadas** (`../network/02`):

- Sem IP público — nenhum node é diretamente alcançável da internet.
- Saída (pull de imagem, API AWS) via **NAT** ou, melhor, **VPC endpoints** (`../network/06`,
  ECR/STS/etc. sem passar pelo NAT).
- Distribuir por **≥2 AZs** (subnet privada por AZ) — se uma AZ cai, o node group continua.

## On-demand vs. spot — a mistura

| | **On-demand** | **Spot** |
|---|---|---|
| Preço | cheio | até ~70-90% menor |
| Interrupção | nenhuma | AWS pode retomar com 2 min de aviso |
| Uso | baseline que **precisa** existir | carga tolerante a interrupção, batch, escala extra |

O padrão desta referência é **misturar**: um node group **on-demand** garante o piso (control
de disponibilidade), um node group **spot** absorve pico/custo. Workloads críticos com
`nodeSelector`/tolerations no on-demand; o resto pode cair no spot. Um `spot: true` no shape do
node group é o que troca o tipo de mercado.

## Sizing — desired / min / max

Cada node group tem três números (Auto Scaling):

```text
size:
  min:     piso — nunca abaixo disso (HA: min ≥ nº de AZs para sobreviver a falha de zona)
  desired: alvo atual
  max:     teto — o quanto pode crescer sob carga
```

- **`min` ≥ 2** (idealmente = nº de AZs) para o baseline on-demand — senão uma falha de AZ ou
  um drain deixa a app sem réplica.
- **`max`** limita o custo e o blast radius de um bug de autoscaling.
- O **Cluster Autoscaler** (ou Karpenter, alvo futuro) ajusta o `desired` entre `min` e `max`
  conforme pods pendentes — não documentado como baseline no PoC ainda.

## 1:N — modelar a lista desde já

O EKS trata node group como recurso 1:N por natureza. Modelar como **objeto único** no
`Cluster.spec` forçaria 1:1 e exigiria uma 2ª migração de schema depois. Decisão:
já nascer com **shape de lista** — `spec.nodeGroups[]` — mesmo fixando 1 node group nesta fatia:

```text
spec:
  nodeGroups:
    - name: <cluster>-workers      # on-demand, baseline
      instanceType: t3.medium
      size: { desired: 3, min: 3, max: 4 }
      subnetIds: [ <privada-AZ-a>, <privada-AZ-b> ]
    - name: <cluster>-workers-spot # spot, elástico
      instanceType: t3.medium
      size: { desired: 2, min: 1, max: 3 }
      spot: true
      subnetIds: [ <privada-AZ-a>, <privada-AZ-b> ]
```

> **Fan-out de N node groups é deferido:** `function-patch-and-transform` não itera arrays — N
> node groups exigem function-kcl (já instalada no Control Plane) ou status-arrays prontos. Por isso a
> fatia fixa `nodeGroups[0]` no código, mantendo o **schema** de lista. Detalhe em
> `../network/07` (open questions) e no tópico 6.

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **[REL10-BP01 — Deploy the workload to multiple locations](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_fault_isolation_multiaz_region_system.html)** | node groups em ≥2 subnets privadas; `min` ≥ nº de AZs |
| **[COST07-BP01 — Perform pricing model analysis](https://docs.aws.amazon.com/wellarchitected/latest/cost-optimization-pillar/cost_pricing_model_analysis.html)** | spot para carga tolerante; on-demand só no baseline |
| **[SEC05 — Protecting networks](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/protecting-networks.html)** | nodes em subnet privada, sem IP público; saída via NAT/endpoints |
| **REL** upgrade seguro | managed node group drena/cicla nodes em update |

## Próximo

→ [`02-addons-and-identity.md`](02-addons-and-identity.md): o que transforma um cluster cru num
cluster com storage, DNS e identidade.
