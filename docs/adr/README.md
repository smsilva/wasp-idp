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
| [0014](0014-single-regional-root-composing-hub-and-cell-modules.md) | Raiz única `regions/<região>` compondo `module.hub` + `module.cell`; revisa 0007 |
| [0015](0015-defer-ipam-adoption.md) | Adiar a adoção do IPAM; supernet passa a ser alocada por região em `/14`; amenda 0003 |
| [0016](0016-documentation-navigation-structure.md) | Estrutura de navegação da documentação: `README.md`/`CLAUDE.md` divididos, portão de entrada na raiz |
| [0017](0017-central-gitops-repo-for-foundry-apps.md) | Repositório GitOps central `wasp-foundry/gitops`: criação por PR, bump de tag por commit direto do CI |
| [0018](0018-separate-github-apps-per-role.md) | Dois GitHub Apps na `wasp-foundry`, um por papel (scaffolding vs. bump de tag) |
| [0019](0019-environment-clusters-managed-by-central-argocd.md) | Clusters `development` e `production` gerenciados pelo ArgoCD do cluster-zero: matrix generator, overlays por ambiente, promoção por PR |
| [0020](0020-catalog-discovery-from-github-org.md) | Catalog descobre os repos da org `wasp-foundry` pelo entity provider do GitHub |
| [0021](0021-keycloak-as-platform-identity-broker.md) | Keycloak, sem Dex, como broker de identidade da plataforma: Google autentica, Keycloak autoriza |
| [0022](0022-kube-api-as-platform-source-of-truth.md) | API do Kubernetes como fonte da verdade da plataforma; Platform API como fachada; Postgres como journal e projeção |
| [0023](0023-platform-catalog-ownership.md) | Catálogo da plataforma: Domain, System e Resource como CRDs, Component e API no repo, Backstage como leitor; resolvedor Forager |
| [0024](0024-component-templates-in-catalog.md) | Templates de component como entidade do catálogo: conteúdo no Git, um padrão por tipo, renderização compatível com o Backstage, import do scaffolder |
| [0025](0025-scm-connections-in-platform-api.md) | SCM connections na Platform API: CRD `ScmConnection` neutro de vendor, GitHub App por manifest flow, segredos atrás de um `SecretStore` |
| [0026](0026-environment-sharing-with-teams.md) | Compartilhamento de ambientes com times: time é grupo do Keycloak sob `/teams`, mantido pela Platform API; `spec.sharedWith` no `Environment`; kubeconfig único na fatia 1; fatia 2 substituída pelo 0028 |
| [0028](0028-environment-personal-credentials.md) | Credencial pessoal de ambiente: token curto de ServiceAccount por pessoa, emitido pela Platform API após `can_use`; kubeconfig com `exec` da CLI; substitui o OIDC no vcluster da fatia 2 do 0026 |
| [0029](0029-cloud-accounts-in-platform-api.md) | Cloud accounts na Platform API: CRD `CloudAccount` neutro de vendor, credencial base mais assume-role com ExternalId, BYO sem aprovação validado pelo controller |
