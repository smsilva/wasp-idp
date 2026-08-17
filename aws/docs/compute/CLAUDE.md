# CLAUDE.md — `compute/` (Domínio: Compute — EKS como Spoke)

> Índice do domínio de **Compute** — o cluster EKS que roda os workloads, modelado como uma
> **spoke** da topologia hub-and-spoke. Ordem de leitura = ordem dos arquivos. Corpo genérico (placeholders `<...>`).

## O que este domínio entrega

Um **cluster EKS pronto para receber deploy** dentro da conta e da rede de um projeto: control
plane, node groups, os add-ons que dão ao cluster identidade (Pod Identity), storage (EBS CSI),
DNS (external-dns), ingress (LB Controller + Istio) e TLS (cert-manager), o modelo de acesso
(RBAC via Access Entries) e a camada de entrega contínua (ArgoCD/GitOps). Cada cluster **é uma
spoke** — sua VPC (`../network/`) attacha ao Hub, seu DNS (`../dns/`) é uma subzona delegada,
sua identidade (`../security/`) usa Pod Identity.

Este domínio é onde os anteriores convergem: rede, DNS, contas e segurança existem para que um
cluster suba de forma reprodutível e isolada. É também o mais **maduro no PoC** — a maior parte
já roda; o texto separa o que existe do que é alvo.

## Tópicos

| # | Arquivo | Assunto | Pilar WAF principal |
|---|---|---|---|
| 0 | [`00-cluster-como-spoke.md`](00-cluster-como-spoke.md) | Anatomia do EKS; control plane vs. data plane; por que cada cluster é uma spoke | Reliability |
| 1 | [`01-node-groups.md`](01-node-groups.md) | Managed node groups; on-demand vs. spot; sizing; 1:N via lista; subnets privadas | Reliability |
| 2 | [`02-addons-e-identidade.md`](02-addons-e-identidade.md) | Add-ons (EBS CSI, Pod Identity agent); Pod Identity/IRSA; a ordem que evita a race | Security |
| 3 | [`03-acesso-e-rbac.md`](03-acesso-e-rbac.md) | `authenticationMode: API`; Access Entries; creator sem admin automático; RBAC do Crossplane | Security |
| 4 | [`04-ingress-e-exposicao.md`](04-ingress-e-exposicao.md) | AWS LB Controller (NLB), Istio gateway, wildcard→NLB, TLS no cluster; exposição via edge | Reliability |
| 5 | [`05-gitops.md`](05-gitops.md) | ArgoCD como satélite; connection secret (kubeconfig) produtor/consumidor; app-of-apps | Operational Excellence |
| 6 | [`06-mapa-crossplane.md`](06-mapa-crossplane.md) | `Cluster` como CR de topo; modelo faseado vs. abstração; estado vs. alvo | — |

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
