# Thin Terraform scope

**Status:** Aceito

## Contexto

Cada componente de plataforma poderia ser entregue por Terraform ou por GitOps (Helm/ArgoCD). Sem
um critério, a tentação é ir empurrando tudo para o Terraform "porque já está aplicando mesmo".

## Decisão

Terraform entrega só: VPC hub + VPC spoke + EKS + nodegroup + Pod Identity base + ESO + ArgoCD +
Crossplane core. E para. `istio`, `cert-manager`, `external-dns`, ALB controller e a
zona/wildcard de DNS vêm por GitOps.

Critério: **cardinalidade × churn**. Recurso que muda pouco e existe uma vez por camada
(VPC, cluster) é Terraform; recurso que muda com frequência ou se repete por aplicação/workload
(charts, configuração de ingress por app) é GitOps.

Rejeitados: **paridade total** (tudo em Terraform, para não ter dois sistemas) e o padrão **seed
cluster / hub-of-hubs** — ambos documentados com o raciocínio completo em `decisions.md` §7.

## Consequências

O cluster nasce "vazio" de Terraform e precisa do wire de GitOps (ArgoCD com credencial de
repositório) para ficar operacional de verdade — essa é a origem do débito rastreado nas issues de
`argocd-gitops`. Qualquer novo componente de plataforma passa primeiro pelo teste de cardinalidade
× churn antes de decidir onde vive.
