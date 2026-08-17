# 00 — O Cluster como Spoke

**Pilar WAF principal:** Reliability (isolamento e HA por design) + Security (blast radius).

## Anatomia do EKS: control plane vs. data plane

Um cluster EKS tem duas metades com donos e ciclos de vida distintos:

| Metade | Quem gerencia | O que é | Custo |
|---|---|---|---|
| **Control plane** | AWS (managed) | API server, etcd, scheduler — multi-AZ, você não vê os nós | fixo por hora, por cluster |
| **Data plane** | você | os node groups (EC2) onde os pods rodam | por instância + EBS + rede |

O control plane é o **gargalo de tempo** (~12-15 min para provisionar) e o custo fixo; o data
plane é o que escala com a carga. Essa separação explica por que "recriar o cluster" custa
caro em tempo (o control plane não tem atalho) — e por que a regra do PoC é **não destruir sem
autorização** (`../../CLAUDE.md`).

## Por que cada cluster é uma spoke

Na topologia hub-and-spoke (`../network/00`), o cluster não é uma ilha — ele **é** uma spoke:

```text
Hub (Connectivity Account)                    Conta do projeto
  Transit Gateway ◄──── attachment ─────  VPC da spoke  ─── EKS control plane
     │                                        │              └─ node groups (data plane)
  VPN de acesso                            subzona DNS delegada (*.<spoke>.<root>)
```

- **A VPC do cluster** é a VPC da spoke (`../network/02`) — subnets públicas (LB) e privadas
  (nodes), attachada ao TGW do Hub quando o multi-account estiver de pé.
- **O DNS do cluster** é a subzona delegada (`../dns/`) — o wildcard aponta ao NLB do cluster.
- **A identidade do cluster** usa Pod Identity com roles escopadas (`../security/04`).
- **O acesso** entra pela VPN que fecha no Hub (`../network/04`), nunca por exposição direta
  do control plane.

Modelar o cluster como spoke é o que dá **isolamento**: um cluster por conta/VPC/subzona, sem
blast radius cruzado. Dois clusters não compartilham nem rede, nem DNS, nem IAM.

## Control plane: as decisões que moldam segurança

Duas escolhas na criação definem a postura do cluster:

- **`authenticationMode: API`** (não `CONFIG_MAP`) — RBAC via **Access Entries** (API da AWS),
  não o antigo `aws-auth` ConfigMap. Mais auditável e declarativo (tópico 3).
- **Endpoint** — público, privado, ou ambos. Numa spoke real, o alvo é **endpoint privado**
  (acesso só via VPN/Hub); o PoC usa endpoint público por praticidade de bootstrap. É uma
  decisão de perímetro, não de funcionalidade.

## Subnets: onde control plane e nodes vivem

- **Control plane ENIs** — precisam de subnets em **≥2 AZs** (HA); podem ser as privadas.
- **Node groups** — sempre nas subnets **privadas** (sem IP público; saída via NAT — tópico 1).
- **Load balancers** — nas subnets **públicas** (internet-facing) ou privadas (internal),
  descobertas por tag (`kubernetes.io/role/elb`) — tópico 4.

O plano de subnets vem de `../network/02`; o cluster só as **referencia** (por ID hoje, por
`networkRef.name` no alvo — tópico 6).

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **REL01** control plane HA | AWS gerencia o control plane multi-AZ; nodes em ≥2 AZs |
| **SEC05** isolamento | cluster = spoke: uma conta, uma VPC, uma subzona, IAM escopado |
| **SEC** perímetro | endpoint privado (alvo) + acesso via VPN no Hub |
| **COST/OPS** ciclo de vida consciente | control plane é o gargalo de tempo/custo — não destruir por reflexo |

## Próximo

→ [`01-node-groups.md`](01-node-groups.md): o data plane — onde os pods de fato rodam.
