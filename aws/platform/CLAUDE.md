# CLAUDE.md — `aws/platform/`

Camada de **provisionamento da topologia** hub-and-spoke via Helm charts sobre os XRDs/
Compositions do Crossplane (que vivem em `../eks/resources/`). Separada de `../eks/` porque
hub e spoke são **rede**, não EKS.

## Charts (`charts/`) — 3 camadas, uma por conceito

| Chart | Renderiza | Conta (providerConfigName) | Custo |
|-------|-----------|----------------------------|-------|
| `hub` | XR `Network` + waiter | `hub` | VPC grátis; NAT/EIP por hora |
| `spoke` | XR `Network` + waiter | `sandbox` (cross-account) | idem |
| `cluster` | `EnvironmentConfig` + XR `Cluster` + waiter | herda (`hub`/`sandbox`) | alto (EKS ~28-30min) |

Cada release provisiona **uma célula** da topologia. Ver `charts/README.md` para ordem de
instalação, pré-requisitos e exemplos.

## Modelo de identidade (Crossplane v2)

A identidade de um XR é o **`metadata.name`** (não há `spec.id` — removido em 2026-08-18). Ele
deriva os external-names (`<prefix>-<metadata.name>-*`) e o label `environment.example.com/env=
<metadata.name>` que casa subnets↔cluster. **Um spoke e o cluster que ele hospeda têm o MESMO
`metadata.name`** (é o que casa as subnets). Gere nomes de spoke/cluster com
`../eks/scripts/random-id` (5 chars a-z0-9). Hub costuma ter um nome legível (ex.: `hub-us-east-1`).

## Fronteiras

- **XRDs/Compositions** (contrato + implementação dos XRs): `../eks/resources/`.
- **Providers/ProviderConfigs/credenciais** (bootstrap): `../eks/providers/` + `../eks/scripts/`.
- **Charts** (orquestração/topologia): aqui. Referenciam os XRs por `apiVersion`
  (`platform.example.com/v1alpha1`), não por path.

## Regra herdada do PoC

Só ADICIONAR recursos isolados; nunca alterar policy/role compartilhada. `providerConfigName`
é OBRIGATÓRIO nos XRs (falha-fechado: XR sem ele é rejeitado, não vaza para o hub).
