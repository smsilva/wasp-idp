# Architecture Decision Records

Decisões de arquitetura deste repositório, formato Nygard (contexto/decisão/consequências). Cada
ADR é imutável depois de aceito — uma decisão revista ganha um ADR novo que referencia o anterior,
nunca edita o antigo. `HANDOFF.md` referencia o ADR relevante em vez de repetir a narrativa.

## Índice

| ADR | Título |
|---|---|
| [0001](0001-provisioning-sequence-skip-phase-1.md) | Sequência de provisionamento pula a Fase 1, indireção de tenant continua obrigatória |
| [0002](0002-thin-terraform-scope.md) | Escopo do Terraform é fino; istio/cert-manager/external-dns/ALB/DNS vêm por GitOps |
| [0003](0003-supernet-cidr-allocation.md) | Alocação de CIDR do supernet `10.0.0.0/12` |
| [0004](0004-centralized-ingress-via-hub.md) | Ingress único, centralizado pelo hub |
| [0005](0005-site-to-site-vpn-per-client.md) | Site-to-Site VPN por cliente, terminando no TGW do hub |
| [0006](0006-client-vpn-saml-for-maintenance-access.md) | Acesso de manutenção via AWS Client VPN + SAML |
| [0007](0007-state-boundary-follows-lifecycle.md) | Fronteira de state segue o ciclo de vida do recurso, não a conta |
| [0008](0008-ingress-alb-nlb-istio-gateway.md) | Ingress variante B: ALB no hub → NLB interno na spoke → istio-ingressgateway |
| [0009](0009-hub-alb-lives-in-connectivity-layer.md) | ALB do hub vive na camada `connectivity/` (T1) |
| [0010](0010-one-acm-wildcard-per-cluster.md) | Um wildcard de ACM por cluster, validado por DNS |
| [0011](0011-nonprod-subzone-delegated-to-route53.md) | Subzona `nonprod.` delegada ao Route 53 da conta `network` |
| [0012](0012-argocd-github-app-auth.md) | GitHub App (não deploy key SSH) para autenticação do ArgoCD |
| [0013](0013-consolidate-local-values-yaml.md) | Consolidar valores locais em `variables/values.yaml`; adiar parametrização formal |
