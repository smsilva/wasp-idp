# 05 — GitOps

**Pilar WAF principal:** Operational Excellence (estado desejado versionado, entrega auditável).

## Por que GitOps fecha o cluster

Provisionar o cluster (control plane, nodes, add-ons) é infraestrutura; **entregar aplicações
nele** é fluxo contínuo. GitOps resolve a segunda metade: o estado desejado das apps vive em
**Git**, e um agente no cluster (**ArgoCD**) reconcilia o cluster para casar com o Git. Deploy
vira `git push`; rollback vira `git revert`; "o que está rodando" é uma pergunta respondida
pelo repositório, não por arqueologia no cluster.

## ArgoCD como satélite do cluster

Nesta referência o ArgoCD é um **satélite** — instalado **no** cluster spoke, mas provisionado
como uma abstração à parte (`ArgoCDInstance`), desacoplada de quem criou o cluster:

```text
Cluster (spoke)  ──publica──►  connection secret (kubeconfig + id + domain)
                                        │
ArgoCDInstance  ──consome──►────────────┘   instala o chart argo-cd NO cluster, via o kubeconfig
```

O desacoplamento produtor/consumidor é deliberado (Platform Engineering 2.0, pilar de
composable design): o `ArgoCDInstance` **não conhece** o cluster diretamente — só o
**connection secret** que o cluster publica (`writeConnectionSecretToRef`). Trocar o cluster
por baixo não muda o contrato do ArgoCDInstance.

## O connection secret — a ponte kubeconfig

O elo é um Secret que o provisionamento do cluster grava e o ArgoCDInstance lê:

| Conteúdo do secret | Para |
|---|---|
| `kubeconfig` | o ArgoCD (via provider-helm) instala o chart no cluster remoto |
| `id` / `domain` | parametrizar a instalação (nome, ingress do ArgoCD sob a subzona) |

É o mesmo padrão de ponte Crossplane→EKS de `../compute/03` (kubeconfig com RBAC via Access
Entry) — aqui aplicado para instalar o ArgoCD, não add-ons.

## App-of-apps — o cluster se popula sozinho

Com o ArgoCD de pé, o padrão **app-of-apps** faz o resto entrar por Git:

```text
Git repo
  └─ root Application (ArgoCD)
       ├─ Application: app1  → namespace, chart/manifests
       ├─ Application: app2
       └─ Application: plataforma (o que não é add-on de infra)
```

Uma `Application` raiz aponta para um diretório de `Application`s; cada uma sincroniza seu
workload. Adicionar um app = adicionar um arquivo no Git — o ArgoCD reconcilia.

## Fronteira: o que é GitOps e o que é Crossplane

Divisão consciente nesta referência:

| Camada | Ferramenta | Exemplo |
|---|---|---|
| **Infra do cluster** (control plane, nodes, add-ons, identidade) | **Crossplane** | EKS, node groups, Pod Identity, LB Controller |
| **Aplicações no cluster** | **GitOps (ArgoCD)** | apps de negócio, config de plataforma |

O PoC hoje faz as **apps como Helm puro fora do Crossplane** (`../../eks/apps/`, ADR decisão 5)
— um degrau; o alvo é essas apps entrarem por ArgoCD/Git. A infra permanece Crossplane; a
aplicação migra para GitOps. Não misturar: Crossplane não deve reconciliar app de negócio, nem
ArgoCD provisionar control plane.

## O rename do campo (alvo)

Decisão: com o `Environment` orquestrador removido e o `Cluster` virando topo, o
`ArgoCDInstance` só muda o **nome do campo** do connection secret:
`environmentConnectionSecretRef` → `clusterConnectionSecretRef`. A mecânica (consumir o secret
publicado) é idêntica — muda o produtor (Cluster, não Environment).

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **[OPS05](https://docs.aws.amazon.com/wellarchitected/latest/operational-excellence-pillar/design-for-operations.html)** estado versionado | apps declaradas em Git; deploy = push, rollback = revert |
| **[OPS06](https://docs.aws.amazon.com/wellarchitected/latest/operational-excellence-pillar/mitigate-deployment-risks.html)** reconciliação contínua | ArgoCD reverte drift automaticamente para o estado do Git |
| **Composable** | ArgoCDInstance consome só o connection secret — desacoplado do produtor |
| **SEC** RBAC do satélite | ArgoCD instala via kubeconfig com Access Entry escopada (`03`) |

## Próximo

→ [`06-mapa-crossplane.md`](06-mapa-crossplane.md): como o cluster inteiro vira o CR de topo
`Cluster`.
