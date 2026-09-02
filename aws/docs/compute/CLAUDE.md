# CLAUDE.md — `compute/` (Domain: Compute — EKS as a Spoke)

> Regras e convenções do domínio de **Compute** — o cluster EKS que roda os workloads,
> modelado como uma **spoke** da topologia hub-and-spoke. Corpo genérico (placeholders
> `<...>`). Índice de leitura em [`README.md`](README.md).

## Sequência de construção (rede pronta → cluster com apps)

```text
① VPC/subnets da spoke prontas (../network/) + subzona DNS delegada (../dns/)
② IAM: roles do cluster e dos add-ons, escopadas <prefix>-* (../security/)
③ Control plane EKS (authenticationMode: API, sem admin automático do creator)
④ Node group(s) gerenciados nas subnets privadas (on-demand + spot)
⑤ Add-ons + Pod Identity: EBS CSI, external-dns, LB Controller, cert-manager, ESO
⑥ Access Entries: dar RBAC ao operador e à automação (Crossplane) — fase explícita
⑦ Ingress: LB Controller materializa o NLB; Istio gateway; wildcard→NLB; TLS por subzona
⑧ GitOps: ArgoCD instalado via connection secret; apps entram por Git
```

## Estado atual vs. alvo (resumo)

- **Hoje no PoC:** um cluster EKS completo sobe via **chart faseado**
  (`../../eks/chart/templates/`, fases 10→106) orquestrado pelo `provision-eks` — control
  plane, node group, todos os add-ons com Pod Identity, RBAC via Access Entries, Istio+NLB,
  cert-manager, ArgoCD. Funciona fim-a-fim (validado end-to-end).
- **Alvo desta referência:** o `Cluster` vira o **CR de topo** (sem `Environment`
  orquestrador), com `nodeGroups[]` como lista, compondo a `Network` (por nome) e o `DnsZone`
  (filho) — uma abstração componível, não uma sequência de fases.
- **Gap central:** migrar do modelo faseado (imperativo-orquestrado) para o `Cluster`
  componível é o Gap 4 de `../network/07` — tópico 6.

## Relação com o resto do repo

- **Consome** `../network/` (VPC/subnets da spoke), `../dns/` (subzona + wildcard),
  `../accounts/` (a conta do projeto), `../security/` (Pod Identity, roles escopadas).
- **Código:** `../../eks/chart/` (modelo faseado atual) e `../../eks/resources/` (abstrações
  `cluster/`, `argocd/`, alvo).
- Regra herdada do PoC (`../../CLAUDE.md`): **nunca destruir o cluster sem autorização
  explícita** (EKS leva ~28-30 min p/ recriar) — vale para toda operação neste domínio.
