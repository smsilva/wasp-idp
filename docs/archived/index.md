# Archive Index

Histórico de itens removidos do `HANDOFF.md` na raiz após conclusão. Cada entrega vive num arquivo
próprio, agrupado por tema, para este índice não crescer sem limite como o antigo `docs/archive.md`
(removido). **Convenção: só se adiciona linha aqui — nunca se apaga uma entrega já arquivada.**

## Bootstrap

- **2026-08-17** — [Crossplane IAM User Bootstrap](bootstrap/crossplane-iam-user.md): IAM user
  `crossplane-poc` criado na conta `hub`, credencial no Secrets Manager.
- **2026-08-17** — [Crossplane Hub On k3d](bootstrap/crossplane-hub-k3d.md): hub Crossplane de pé no
  k3d local, credencial consumida via `ProviderConfig`.

## Accounts

- **2026-08-24/25** — [Frontier A — Accounts](accounts/frontier-a-accounts.md): OUs, SCPs baseline,
  CloudTrail organizacional, conta `cicd`.

## Documentation

- **2026-08-24/26** — [Frontier C — Documentation](documentation/frontier-c-documentation.md):
  domínio `tenancy/`, hierarquia de fontes WAF → whitepaper → SRA.

## Terraform layers

- **2026-08-25** — [Terraform Layer 1 — Network Foundation](terraform-layers/layer-1-network-foundation.md):
  bucket de state, VPC hub, reuso de módulo entre regiões.
- **2026-08-25/26** — [Terraform Layer 2 — Control Plane](terraform-layers/layer-2-control-plane.md):
  VPC spoke + EKS + node group + Pod Identity + ESO/ArgoCD/Crossplane, escrita/aplicada/destruída.
- **2026-08-26** — [Terraform Layers Ported To The Corporate Track](terraform-layers/port-to-corporate-track.md):
  `aws/terraform/` levada para a trilha corporativa, genericizada.

## Private access

- **2026-08-26** — [Reference Design Comparison — PrivateLink Vs TGW](private-access/reference-design-comparison.md):
  comparação com o desenho hub-and-spoke de referência, resolução PrivateLink vs TGW.
- **2026-08-26** — [Private Access And Ingress Plan Closed](private-access/access-plan-closed.md):
  plano de quatro fases fechado, nove decisões.
- **2026-08-26** — [Step 1.1 — LBC Discovery Tags](private-access/step-1-1-lbc-tags.md): tags de
  descoberta do LBC já existiam; teste que faltava foi escrito.
- **2026-08-26** — [Step 1.2 — EKS API Endpoint Restricted](private-access/step-1-2-api-endpoint-restricted.md):
  endpoint da API restrito ao IP de quem aplica, sem default.
- **2026-08-26** — [Step 1.3 — DNS Root](private-access/step-1-3-dns-root.md): raiz `dns/` escrita,
  subzona + delegação cross-cloud.
- **2026-08-26** — [Bring-Up Scripts And DNS Layer Applied](private-access/dns-layer-applied.md):
  `aws/terraform/scripts/` por camada + camada 2 de DNS aplicada e verificada.
- **2026-08-26** — [Step 2.1 — AWS VPN Client Gate](private-access/step-2-1-vpn-client-gate.md):
  client 6.0.1 scriptável, portão passado.
- **2026-08-26** — [Step 2.2 — Connectivity Root](private-access/step-2-2-connectivity-root.md): raiz
  `connectivity/` escrita (TGW, Client VPN, certificado ACM).
- **2026-08-26** — [Step 2.2 — Connectivity Apply](private-access/step-2-2-apply.md): apply na AWS,
  túnel `Connected`, as duas perguntas do aceite resolvidas.
- **2026-08-26** — [Step 2.3 — Spoke Joins The Mesh](private-access/step-2-3-spoke-joins-mesh.md):
  spoke entra na malha via TGW, ping real, teardown exercitado.
- **2026-08-27** — [Steps 2.4+2.5 — EKS Private Endpoint](private-access/step-2-4-2-5-eks-private-endpoint.md):
  SG rule para o endpoint privado, endpoint público fechado por default.

## Provisioning sequence

- **2026-08-27** — [Provisioning Sequence And Resource Dictionary](provisioning-sequence/sequence-and-resource-dictionary.md):
  sequência autoritativa `00`→`08` + dicionário de 61 recursos.
