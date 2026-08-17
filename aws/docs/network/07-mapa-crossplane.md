# 07 — Mapa para Crossplane

**Ponte entre a arquitetura (tópicos 0–6) e o código.** Mostra que XRD/Composition
materializa cada peça, o que **já roda no PoC hoje**, o que é **alvo**, e o **gap** entre os
dois — com o caminho de migração.

## Modelo de composição (composable design)

A arquitetura é materializada por **XRs componíveis** — um recurso de alto nível compõe os
de baixo, nada é monolítico (Pilar 5, "Platform Engineering 2.0"):

```text
                (alvo multi-account)
   HubNetwork ──► TGW + tgw-rt-hub + VPN Connections + RAM shares
        ▲
        │ RAM / attachment
        ▼
   Cluster ──► Spoke(VPC+subnets+attachment) + DnsZone + node groups + add-ons
        │
        ├──► Network   (a pegada de rede do spoke — VPC/subnets/NAT/routes)
        └──► DnsZone   (subzona pública + NS + wildcard)
```

## Estado atual no PoC (o que já existe)

| Peça da arquitetura | XRD/Composition | Arquivo | Estado |
|---|---|---|---|
| VPC + 4 subnets + IGW/NAT + routes (16 MRs) | `Network` (`platform.example.com/v1alpha1`) | `../../eks/resources/network/` | ✅ roda, single-account |
| Cluster EKS + node group + auth | `Cluster` | `../../eks/resources/cluster/` | ✅ roda |
| Orquestrador Network+Cluster | `Environment` | `../../eks/resources/environment/` | ⚠️ a remover |
| ArgoCD no cluster | `ArgoCDInstance` | `../../eks/resources/argocd/` | ✅ roda |
| **HubNetwork (TGW/VPN/RAM)** | — | — | ❌ não existe |
| **DnsZone (subzona pública)** | — | — | ❌ não existe (planejado) |

**Referência externa madura** (KCL, a portar/adaptar): os templates `hub_network` e
`spoke_network` da organização em `<assets-repo>/crossplane/providers/aws/` já
implementam TGW, VPN, RAM e isolamento por tenant. São a fonte-verdade do padrão hub-spoke.

## Contrato de saída da `Network` atual

A `Network` do PoC já segue o padrão composable esperado de um spoke (tópico 2):

- **Publica** `status.vpcId` e `status.subnetIds.{publicA,publicB,privateA,privateB}`.
- **Taggeia** cada subnet com `environment.example.com/{role,tier,cluster-subnet}` +
  `Name` determinístico (`<prefix>-<id>-<papel>`).
- **Isola** por label `environment.example.com/env=<id>` em todos os 16 MRs — o
  discriminador que impede um Cluster de casar subnets de outro Environment no mesmo hub.
- **Naming**: NÃO seta `crossplane.io/external-name` em recurso cujo ID é gerado pela AWS
  (VPC, Subnet, IGW, EIP, NAT, RouteTable, Route, RTA) — setá-lo faria o provider tentar
  ADOTAR um recurso inexistente. Nome amigável vai em `tags.Name`.

## Gaps entre atual e alvo

### Gap 1 — CIDR hardcoded (bloqueante para hub-and-spoke)

**Hoje:** `cidrBlock: 172.16.0.0/16` fixo na Composition; subnets `172.16.{1,2,3,4}.0/24`
fixas.

**Problema:** todo spoke nasceria idêntico → sobreposição → impossível attachar 2 ao mesmo
TGW (tópico 1). E `172.16` fica fora da supernet `10.x` da referência.

**Direção decidida (brainstorm):**
- Adicionar `spec.vpcCidrSecondOctet` (ou equivalente) — formato `<base>.<N>.0.0/16`, `N`
  validado por `pattern` no XRD.
- Derivar as 4 subnets por **string-format em patch-and-transform** (sem function-kcl):
  `<base>.<N>.1.0/24` … `<base>.<N>.4.0/24`.
- Alinhar `<base>` à supernet planejada para o ambiente (`<supernet>`).

**Validação pendente:** confirmar que o `CombineFromComposite`/string-format monta os `/24`
corretamente a partir de `N` (o XRD restringe `N` por regex; sem KCL).

### Gap 2 — sem HubNetwork / TGW / VPN

A `Network` atual é uma VPC solta (IGW+NAT), não um spoke attachado a um TGW. Para virar
spoke de verdade:
- Criar um XR **HubNetwork** (TGW + `tgw-rt-hub` + VPN Connections + RAM), 1× por região —
  portar do `hub_network` KCL da organização.
- Estender a `Network` (ou o Cluster que a compõe) com **TGW attachment + `tgw-rt-<spoke>` +
  propagação** — portar do `spoke_network` KCL.
- **Decisão desta fatia:** **NÃO** criar TGW/attachment agora (PoC isolado, sem tráfego
  cross-account). Apenas **parametrizar o CIDR** (Gap 1) para não exigir re-endereçamento
  quando o TGW chegar. O resto é mapeado para o futuro.

### Gap 3 — DnsZone ainda não é XR

O DNS público por spoke (tópico 5) hoje é feito por external-dns no cluster + zona pai
manual. Alvo: um XR **DnsZone** (Zone + Record NS na pai + Record wildcard A-alias→LB),
composto como **filho do Cluster**. Planejado, ainda não escrito.

### Gap 4 — Environment orquestrador (a remover)

Decisão: o `Cluster` vira o **CR de topo** (sem `Environment` por cima);
`domain`/Route53 embutidos no Cluster; `Network` referenciada por nome
(`Cluster.spec.networkRef.name`) com patch cross-XR direto, sem label/selector. O
`Environment` (`environment/{xrd,composition,environmentconfig}.yaml`) sai desta fatia.

## Config compartilhada do hub (EnvironmentConfig)

Valores do hub que a Composition lê (não hardcode): `crossplaneArn`, `prefix`,
`parentHostedZoneId`, `canonicalNlbZoneId`. Vivem num EnvironmentConfig na raiz de
`resources/` (`hub-config.yaml`, planejado) — o Cluster os lê via `FromEnvironmentFieldPath`.
Valores reais no apêndice.

## Ordem de implementação sugerida (quando sair do design)

1. `Network`: parametrizar CIDR (Gap 1) + migrar grupo para `aws.example.com` + remover
   `spec.id` (naming por `<prefix>-<metadata.name>`).
2. `Cluster`: virar topo, `networkRef.name`, `domain`, `nodeGroups[0]`, compor `DnsZone`.
3. `DnsZone`: XR novo (Gap 3).
4. Remover `environment/` (Gap 4); renomear campo no `argocd/`.
5. Validar no hub k3d: dry-run → real (reusar a VPC de teste existente).
6. **Futuro** (mapeado, não agora): `HubNetwork` + attachment/RAM (Gap 2).
