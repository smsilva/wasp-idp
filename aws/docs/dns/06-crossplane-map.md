# 06 — Crossplane Map

> Como o DNS desta referência vira XRD/Composition — o XR `DnsZone`, a divisão de
> responsabilidade com external-dns, o estado atual do PoC e o gap até o alvo. Fecha o domínio
> ligando a arquitetura ao código.

## A divisão de responsabilidade: Crossplane vs. external-dns

Duas automações escrevem DNS, em camadas diferentes — não competem, se complementam:

| Camada | Quem | Escreve | Ciclo de vida |
|---|---|---|---|
| **Estrutural** | Crossplane (`DnsZone`) | a subzona, o NS na pai, o wildcard→NLB | vive/morre com o **Cluster** |
| **Por-app** | external-dns (no cluster) | A-records por Service/Ingress | vive/morre com o **workload** |

Regra: o que é **infraestrutura da subzona** (existe enquanto o cluster existe) é do
Crossplane; o que é **por app** (aparece e some com o deploy) é do external-dns. No modelo
**wildcard preferido** (tópico 4), o external-dns por app quase desaparece — o wildcard do
`DnsZone` já resolve todos os apps, e o external-dns fica para casos que precisam de record
dedicado.

## O XR `DnsZone` (alvo — ainda não escrito)

Decisão ratificada: DNS deixa de ser lógica espalhada e vira uma **abstração
componível**, **filha do Cluster**:

```text
Cluster (CR de topo)
  └─► DnsZone            [XR novo]
        ├─ Zone            subzona <spoke>.<root-domain>   (route53 Zone; SEM region — Route53 é global)
        ├─ Record NS       na PAI, lendo os NS da Zone.status  (delegação — tópico 1)
        └─ Record wildcard *.<spoke>...  A-alias → NLB  (HostedZoneId = canonicalNlbZoneId; nlbHostname opcional)
```

Kinds do `provider-aws-route53`: `Zone` (`route53.aws.upbound.io/v1beta1`), `Record`
(`v1beta2`). Pontos do design já decididos:

- **`Zone` não tem `region`** — Route53 é global; não patchar região nela.
- **NS lido do status**, não hardcoded — o Record NS de delegação referencia
  `Zone.status.atProvider.nameServers` (os 4 NS reais), TTL baixo (60).
- **Wildcard opcional** via `nlbHostname` — só materializa o Record wildcard se o hostname do
  NLB for conhecido; senão cria só Zone + NS (o LB pode não existir no momento da criação).
- **`canonicalNlbZoneId`** vem do config do Control Plane (EnvironmentConfig `control-plane-config.yaml`, lido via
  `FromEnvironmentFieldPath`), não hardcoded — junto com `parentHostedZoneId` e `prefix`.

## Config do Control Plane que o `DnsZone` consome

Do `control-plane-config.yaml` (EnvironmentConfig na raiz de `resources/`, planejado):

| Campo | Papel no DNS |
|---|---|
| `parentHostedZoneId` | onde o Record NS de delegação é escrito (a zona pai) |
| `canonicalNlbZoneId` | o `HostedZoneId` do AliasTarget do wildcard (zona canônica do ELB na região) |
| `prefix` | naming determinístico `<prefix>-<metadata.name>` das Zones/Records |

## Estado atual do PoC vs. alvo

| Peça | Estado no PoC | Alvo |
|---|---|---|
| Subzona por ambiente | ✅ criada via `Zone`/`Record` (`provider-aws-route53`), lógica espalhada | XR `DnsZone` componível, filho do Cluster |
| Record NS na pai | ✅ criado (TTL 60), lendo NS da subzona | idem, dentro do `DnsZone` |
| Wildcard A-alias→NLB | ✅ criado (`canonicalNlbZoneId` `us-east-1`) | idem, `nlbHostname` opcional |
| external-dns | ✅ roda escopado (`--zone-id-filter`/`--txt-owner-id`, `upsert-only`) | mantém — camada por-app, complementar ao wildcard |
| cert-manager DNS-01 | ✅ issuer **por subzona** (fix do TXT na zona errada) | mantém; policy IAM inclui ARN da subzona |
| **`DnsZone` como XR** | ❌ **não existe** — Gap 3 do [`network/07-crossplane-map.md`](../network/07-crossplane-map.md) | escrever o XRD + Composition |
| Grupo de API | `platform.example.com` (a migrar) | `aws.example.com` (Network/Cluster/DnsZone) |

## Ordem de implementação sugerida

1. Definir o **XRD `DnsZone`** (grupo `aws.example.com`): `spec.domain` (FQDN da subzona),
   `spec.nlbHostname?`; lê `parentHostedZoneId`/`canonicalNlbZoneId` do EnvironmentConfig.
2. **Composition** (patch-and-transform puro): `Zone` + `Record` NS (do status) + `Record`
   wildcard (condicional a `nlbHostname`).
3. Compor o `DnsZone` como **filho do Cluster** (o Cluster passa `domain`/`nlbHostname`).
4. Manter external-dns e o issuer por subzona como estão (complementares).
5. Validar no Control Plane (k3d): dry-run → real (reusar a subzona/zona pai existentes).

> Depende do refactor maior de [`network/07-crossplane-map.md`](../network/07-crossplane-map.md) (Cluster vira topo, `control-plane-config.yaml`, grupo de
> API novo). O `DnsZone` é o Gap 3 daquele mapa — este domínio é a especificação de DNS que o
> alimenta.
