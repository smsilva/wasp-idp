# 06 — Mapa para Crossplane

> Como o cluster inteiro vira o CR de topo `Cluster` — a transição do modelo faseado
> (imperativo-orquestrado) para a abstração componível, o estado atual do PoC e os gaps. Fecha
> o domínio ligando a arquitetura ao código.

## Dois modelos: faseado (hoje) vs. componível (alvo)

| | **Faseado (atual)** | **Componível (alvo)** |
|---|---|---|
| Forma | chart Helm com fases 10→106, orquestradas por `provision-eks` | XR `Cluster` como CR de topo, uma Composition |
| Ordem | sequência imperativa (o script aplica fase, espera, avança) | dependências declarativas (readiness entre MRs) |
| Node groups | fase `60-nodegroup` (1) | `spec.nodeGroups[]` (lista, `[0]` fixado nesta fatia) |
| Rede | fases `10-20-30` embutidas | `Network` referenciada por `networkRef.name` (cross-XR) |
| DNS | fases `86-88` + Route53 solto | XR `DnsZone`, **filho** do Cluster (`../dns/06`) |
| Orquestrador | `Environment` (a remover) | **sem** `Environment` — `Cluster` é o topo |

O faseado **funciona fim-a-fim** (validado end-to-end); o componível é o destino ratificado. A
migração é o Gap 4 de `../network/07`.

## O `Cluster` como CR de topo (alvo)

```text
Cluster (aws.example.com)          [CR de topo — sem Environment por cima]
  spec:
    domain: <spoke>.<root-domain>        → compõe DnsZone (filho)
    networkRef.name: <network>           → lê Network.status.subnetIds (patch cross-XR direto)
    region, nodeGroups[]                 → control plane + node group(s)
  compõe:
    ├─ EKS control plane (authenticationMode: API)
    ├─ NodeGroup(s)         (../compute/01)
    ├─ Add-ons + Pod Identity (../compute/02)
    ├─ Access Entries       (../compute/03)
    └─ DnsZone (filho)      (../dns/06)
```

Pontos de design decididos:

- **Grupo de API** migra para `aws.example.com` (Network, Cluster, DnsZone); sem `spec.id`;
  naming `<prefix>-<metadata.name>`.
- **`Network` por nome** — `Cluster.spec.networkRef.name` → Composition lê
  `Network.status.subnetIds` via `FromCompositeFieldPath` cross-XR **direto** (sem
  label/selector).
- **`DnsZone` é filho do Cluster** — o Cluster passa `domain`/`nlbHostname`; o DnsZone
  materializa Zone + NS + wildcard.
- **`nodeGroups[]` shape de lista** já no schema, `[0]` implementado (evita 2ª migração —
  `../compute/01`).
- **Config do Control Plane** (`control-plane-config.yaml`, EnvironmentConfig na raiz): `crossplaneArn`, `prefix`,
  `parentHostedZoneId`, `canonicalNlbZoneId` — lidos via `FromEnvironmentFieldPath`.

## Estado atual do PoC vs. alvo

| Peça | Estado no PoC | Alvo |
|---|---|---|
| Control plane EKS | ✅ fase `50-eks` (`authenticationMode: API`) | MR dentro do `Cluster` |
| Node group | ✅ fase `60` (1 node group) | `spec.nodeGroups[]` (`[0]` fixo) |
| Add-ons + Pod Identity | ✅ fases `65/68/80-92/100` (EBS, ESO, external-dns, LB, cert-manager) | idem, compostos pelo Cluster |
| Access Entries (RBAC) | ✅ fases `70/72` (operador + Crossplane) | idem |
| Ingress (NLB + Istio) | ✅ fases `92/94/96/98` | idem |
| DNS | ✅ fases `86/88` + Route53 solto | XR `DnsZone` filho (`../dns/06`, Gap 3) |
| `Cluster` como topo | ⚠️ XR `Cluster` existe mas sob `Environment`, grupo `platform.*` | topo, grupo `aws.*`, sem `Environment` |
| `Environment` orquestrador | ✅ existe (`environment/`) | **removido** (Gap 4) |
| ArgoCD | ✅ `ArgoCDInstance` (connection secret) | só rename `environment*`→`cluster*` (`../compute/05`) |
| Apps de negócio | ⚠️ Helm puro fora do Crossplane (`apps/`) | GitOps via ArgoCD (`../compute/05`) |

## Ordem de implementação sugerida

1. `Cluster`: virar CR de topo — grupo `aws.example.com`, `networkRef.name`, `domain`,
   `nodeGroups[]` (`[0]`), sem `spec.id`.
2. Compor o **DnsZone** como filho (`../dns/06`, Gap 3).
3. Remover o **`Environment`** (`environment/{xrd,composition,environmentconfig}.yaml`) — Gap 4.
4. **Rename** do campo no `ArgoCDInstance` (`environmentConnectionSecretRef` →
   `clusterConnectionSecretRef`).
5. Validar no Control Plane (k3d): dry-run → real (reusar a `Network net01` existente — não reprovisionar).
6. **Futuro** (mapeado, não agora): fan-out de N node groups (function-kcl); Karpenter;
   endpoint privado; attachment/RAM ao TGW (`../network/07`, Gap 2).

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **OPS05** infra como código | cluster inteiro num CR declarativo, não sequência de scripts |
| **Composable** | Cluster compõe Network (por nome) + DnsZone (filho); ArgoCD desacoplado |
| **REL** reprodutível | 1 claim → cluster completo; readiness declarativo entre MRs |
