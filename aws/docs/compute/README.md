# `compute/` — Domain: Compute — EKS as a Spoke

Índice de leitura. Convenções e regras ficam em [`CLAUDE.md`](CLAUDE.md).

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
| 0 | [`00-cluster-as-spoke.md`](00-cluster-as-spoke.md) | Anatomia do EKS; control plane vs. data plane; por que cada cluster é uma spoke | Reliability |
| 1 | [`01-node-groups.md`](01-node-groups.md) | Managed node groups; on-demand vs. spot; sizing; 1:N via lista; subnets privadas | Reliability |
| 2 | [`02-addons-and-identity.md`](02-addons-and-identity.md) | Add-ons (EBS CSI, Pod Identity agent); Pod Identity/IRSA; a ordem que evita a race | Security |
| 3 | [`03-access-and-rbac.md`](03-access-and-rbac.md) | `authenticationMode: API`; Access Entries; creator sem admin automático; RBAC do Crossplane | Security |
| 4 | [`04-ingress-and-exposure.md`](04-ingress-and-exposure.md) | AWS LB Controller (NLB), Istio gateway, wildcard→NLB, TLS no cluster; exposição via edge | Reliability |
| 5 | [`05-gitops.md`](05-gitops.md) | ArgoCD como satélite; connection secret (kubeconfig) produtor/consumidor; app-of-apps | Operational Excellence |
| 6 | [`06-crossplane-map.md`](06-crossplane-map.md) | `Cluster` como CR de topo; modelo faseado vs. abstração; estado vs. alvo | — |
