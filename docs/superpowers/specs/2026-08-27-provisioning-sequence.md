# Provisioning sequence — this repository

Authoritative order in which this repository provisions AWS, layer by layer, from an empty
Organization up to a workload reachable over the tunnel. Reviewed against `aws/docs/accounts/`,
every root under `aws/terraform/`, and the plan set in
`docs/superpowers/plans/2026-08-26-private-access-and-ingress/`.

This supersedes [`2026-08-20-provisioning-sequence.md`](2026-08-20-provisioning-sequence.md), which
is kept only as a historical portrait of a Crossplane monolith from the corporate trail — that one
starts at the VPC and mixes concerns this repo separates. The sequence here is broader: it starts at
account bootstrap and ends at the spoke.

**How to read (YAML):** **nesting = primary blocker** (the parent is provisioned first). Comments:
`# needs:` = additional dependency (besides the parent) · `# reads:` = data source into another
layer · `# →` = what it produces · `# not created:` = present in the module but gated off here.
`outputs:` = the contract the layer publishes to the next ones. `state:` = which Terraform state
owns the resource. Below each block, the **Definitions** links point to each resource's file (index
in the [resource dictionary](2026-08-27-resource-dictionary.md)).

**Status legend:** ✅ applied · ♻️ applied and torn down (proven, not currently up) · ⏳ written, not
yet applied · 📋 planned, no code yet.

---

## 00 · accounts — pre-Terraform, CLI and console only  ✅

Not Terraform. Everything below is `aws/docs/accounts/scripts/`, run once, by hand.

```yaml
management-account:               # the account you already had
  organization:                   # feature-set ALL — SCPs do not work under consolidated billing
    ou-structure:                 # Security, Infrastructure, Deployments, Workloads/{NonProd,Production}
      log-archive-account:        # OU Security · created FIRST: no trail = no record of the bootstrap
        log-archive-bucket:       # needs: OrganizationAccountAccessRole into log-archive
        organization-trail:       # needs: trusted access for cloudtrail · multi-region, log-file validation
      baseline-scps:              # attach before creating accounts — create-account lands at Root, then moves
        - DenyLeaveOrganization         # Root
        - ProtectCloudTrail             # Root
        - DenyOutsideApprovedRegions    # per OU · region list is org-wide, not per account
        - RequireImdsv2                 # per OU
        - DenyRootUser                  # per OU
      network-account:            # OU Infrastructure · hosts hub VPC, TGW, Client VPN, the state bucket
      cicd-account:               # OU Deployments · hosts the control-plane cluster
    identity-center:              # permission sets assigned to GROUPS, not users
      saml-application:           # console only · gates layer 04 (Client VPN federation)

outputs:
  organization-id:
  ou-ids:
  network-account-reachable:      # via permission set or OrganizationAccountAccessRole
  cicd-account-reachable:
  approved-regions:               # every later layer fails at its first Create* if its region is not here
```

**Definitions:** [organization](2026-08-27-resource-dictionary/organization.md) · [ou-structure](2026-08-27-resource-dictionary/ou-structure.md) · [baseline-scps](2026-08-27-resource-dictionary/baseline-scps.md) · [log-archive-bucket](2026-08-27-resource-dictionary/log-archive-bucket.md) · [organization-trail](2026-08-27-resource-dictionary/organization-trail.md) · [identity-center](2026-08-27-resource-dictionary/identity-center.md) · [saml-application](2026-08-27-resource-dictionary/saml-application.md) · [organization-account-access-role](2026-08-27-resource-dictionary/organization-account-access-role.md)

## 01 · state-backend  ✅

`aws/terraform/state-backend/` · state key `state-backend/terraform.tfstate` · account `network`.

```yaml
aws_s3_bucket.this:               # prevent_destroy · self-hosted: its own state lives inside it
  aws_s3_bucket_versioning.this:
  aws_s3_bucket_server_side_encryption_configuration.this:
  aws_s3_bucket_public_access_block.this:
  aws_s3_bucket_ownership_controls.this:
  aws_s3_bucket_policy.this:      # needs: public_access_block (AWS rejects the policy otherwise)

outputs:
  bucket_name:                    # every later layer's -backend-config=bucket=
  bucket_arn:
```

**Definitions:** [aws_s3_bucket](2026-08-27-resource-dictionary/aws_s3_bucket.md) · [aws_s3_bucket_versioning](2026-08-27-resource-dictionary/aws_s3_bucket_versioning.md) · [aws_s3_bucket_server_side_encryption_configuration](2026-08-27-resource-dictionary/aws_s3_bucket_server_side_encryption_configuration.md) · [aws_s3_bucket_public_access_block](2026-08-27-resource-dictionary/aws_s3_bucket_public_access_block.md) · [aws_s3_bucket_ownership_controls](2026-08-27-resource-dictionary/aws_s3_bucket_ownership_controls.md) · [aws_s3_bucket_policy](2026-08-27-resource-dictionary/aws_s3_bucket_policy.md)

## 02 · network-foundation — the hub VPC, one root per region  ✅

`aws/terraform/network-foundation/<region>/` · state key `network-foundation/<region>/terraform.tfstate`
· account `network` · module `src/network`. Permanent and deliberately zero-cost: `enable_nat_gateway
= false`, because nothing routes through the hub until a TGW exists.

```yaml
aws_vpc.this:                     # 10.1.0.0/16 in us-east-1 · 10.3.0.0/16 in us-west-2
  aws_subnet.public[0,1]:         # one per AZ
  aws_subnet.private[0,1]:
  aws_internet_gateway.this:
  aws_route_table.public:
    aws_route.public_default:     # needs: aws_internet_gateway.this
    aws_route_table_association.public[*]:
  aws_route_table.private:
    aws_route_table_association.private[*]:
    aws_route.private_default[0]: # not created: enable_nat_gateway = false
  aws_eip.nat[0]:                 # not created
    aws_nat_gateway.this[0]:      # not created

outputs:
  hub_vpc_id:
  hub_vpc_cidr:
  hub_private_subnet_ids:
  hub_control_plane_subnet_ids:
```

**Definitions:** [aws_vpc](2026-08-27-resource-dictionary/aws_vpc.md) · [aws_subnet](2026-08-27-resource-dictionary/aws_subnet.md) · [aws_internet_gateway](2026-08-27-resource-dictionary/aws_internet_gateway.md) · [aws_route_table](2026-08-27-resource-dictionary/aws_route_table.md) · [aws_route](2026-08-27-resource-dictionary/aws_route.md) · [aws_route_table_association](2026-08-27-resource-dictionary/aws_route_table_association.md) · [aws_eip](2026-08-27-resource-dictionary/aws_eip.md) · [aws_nat_gateway](2026-08-27-resource-dictionary/aws_nat_gateway.md)

## 03 · dns — the delegated subzone  ✅

`aws/terraform/dns/` · state key `dns/terraform.tfstate` (no region — hosted zones are global) ·
providers: `aws` (account `network`), `aws.management` alias, `azurerm` (the parent zone).

```yaml
aws_ram_sharing_with_organization.this:   # provider aws.management · one-off, permanent
                                          # → gates the cross-account TGW share in layer 05
aws_route53_zone.subzone:                 # prevent_destroy · the nonprod subzone
  azurerm_dns_ns_record.delegation[0]:    # needs: subzone.name_servers · gate: var.manage_delegation

outputs:
  subzone_name:
  subzone_id:
  subzone_name_servers:
  delegation_managed:
```

**Definitions:** [aws_ram_sharing_with_organization](2026-08-27-resource-dictionary/aws_ram_sharing_with_organization.md) · [aws_route53_zone](2026-08-27-resource-dictionary/aws_route53_zone.md) · [azurerm_dns_ns_record](2026-08-27-resource-dictionary/azurerm_dns_ns_record.md)

## 04 · connectivity — TGW and the maintenance tunnel  ⏳

`aws/terraform/connectivity/us-east-1/` · state key `connectivity/us-east-1/terraform.tfstate` ·
account `network`. Costs money per hour; torn down when not in use.

```yaml
reads:                            # by tag/name via data sources — never terraform_remote_state
  data.aws_vpc.hub:               # from 02
  data.aws_subnets.hub_private:   # from 02
  data.aws_route_table.hub_private:  # from 02
  data.aws_route53_zone.subzone:  # from 03

aws_ec2_transit_gateway.hub:      # default association AND propagation disabled — isolation by default
  aws_ec2_transit_gateway_route_table.hub:
  aws_ec2_transit_gateway_vpc_attachment.hub:
    aws_ec2_transit_gateway_route_table_association.hub:
    aws_route.hub_to_tgw:         # in the hub private route table · needs: attachment.hub
  aws_ram_resource_share.tgw:
    aws_ram_resource_association.tgw:
    aws_ram_principal_association.spoke[*]:   # one per spoke account id

aws_acm_certificate.vpn:          # public cert, DNS-validated · create_before_destroy
  aws_route53_record.vpn_validation:          # needs: data.aws_route53_zone.subzone
    aws_acm_certificate_validation.vpn:

aws_iam_saml_provider.client_vpn: # reads the metadata XML exported from Identity Center (layer 00)
  aws_ec2_client_vpn_endpoint.hub:            # needs: acm_certificate_validation.vpn, data.aws_vpc.hub
    aws_ec2_client_vpn_network_association.hub[*]:     # one per hub private subnet · ~7-10 min each
      aws_ec2_client_vpn_route.supernet[*]:   # needs: network_association (for_each alone is not enough)
    aws_ec2_client_vpn_authorization_rule.operators[*]:  # gate: var.manage_authorization · per group

outputs:
  transit_gateway_id:
  transit_gateway_route_table_id:
  transit_gateway_attachment_id:
  client_vpn_endpoint_id:
  client_vpn_dns_name:
  server_certificate_domain:
  authorized_group_ids:
```

**Definitions:** [aws_ec2_transit_gateway](2026-08-27-resource-dictionary/aws_ec2_transit_gateway.md) · [aws_ec2_transit_gateway_route_table](2026-08-27-resource-dictionary/aws_ec2_transit_gateway_route_table.md) · [aws_ec2_transit_gateway_vpc_attachment](2026-08-27-resource-dictionary/aws_ec2_transit_gateway_vpc_attachment.md) · [aws_ec2_transit_gateway_route_table_association](2026-08-27-resource-dictionary/aws_ec2_transit_gateway_route_table_association.md) · [aws_ram_resource_share](2026-08-27-resource-dictionary/aws_ram_resource_share.md) · [aws_ram_resource_association](2026-08-27-resource-dictionary/aws_ram_resource_association.md) · [aws_ram_principal_association](2026-08-27-resource-dictionary/aws_ram_principal_association.md) · [aws_acm_certificate](2026-08-27-resource-dictionary/aws_acm_certificate.md) · [aws_route53_record](2026-08-27-resource-dictionary/aws_route53_record.md) · [aws_acm_certificate_validation](2026-08-27-resource-dictionary/aws_acm_certificate_validation.md) · [aws_iam_saml_provider](2026-08-27-resource-dictionary/aws_iam_saml_provider.md) · [aws_ec2_client_vpn_endpoint](2026-08-27-resource-dictionary/aws_ec2_client_vpn_endpoint.md) · [aws_ec2_client_vpn_network_association](2026-08-27-resource-dictionary/aws_ec2_client_vpn_network_association.md) · [aws_ec2_client_vpn_route](2026-08-27-resource-dictionary/aws_ec2_client_vpn_route.md) · [aws_ec2_client_vpn_authorization_rule](2026-08-27-resource-dictionary/aws_ec2_client_vpn_authorization_rule.md)

## 05 · control-plane — the first spoke  ✅ (TGW pieces ♻️)

`aws/terraform/control-plane/` · state key `control-plane/terraform.tfstate` · account `cicd`, with
an `aws.network` aliased provider for the hub-side pieces whose lifecycle is the spoke's. One
`terraform apply` spans the `aws`, `kubernetes` and `helm` providers — the last two configured from
this same root's own cluster outputs.

```yaml
reads:                                      # all via provider aws.network, by tag
  data.aws_vpc.hub:                         # from 02
  data.aws_ec2_transit_gateway.hub:         # from 04
  data.aws_ec2_transit_gateway_route_table.hub:   # from 04
  data.aws_ec2_transit_gateway_vpc_attachment.hub:  # from 04

module.network:                             # src/network again · 10.2.0.0/16 · NAT enabled here
  # → vpc, subnets, igw, eip, nat, route tables, routes, associations (see layer 02 for the shape)

aws_ec2_transit_gateway_vpc_attachment.this:      # spoke side · needs: module.network, data.tgw.hub
                                                  # ignore_changes on default assoc/propagation
  aws_ec2_transit_gateway_vpc_attachment_accepter.this:   # provider aws.network · the second gate
    aws_ec2_transit_gateway_route_table.spoke:            # provider aws.network · the tenant table
      aws_ec2_transit_gateway_route_table_association.spoke:
      aws_ec2_transit_gateway_route_table_propagation.spoke_to_hub:
      aws_ec2_transit_gateway_route_table_propagation.hub_to_spoke:  # direction is reversed on purpose
    aws_route.spoke_to_hub:                 # in the spoke private route table

module.cluster:                             # src/cluster
  aws_iam_role.cluster:
    aws_iam_role_policy_attachment.cluster:
  aws_iam_role.node:
    aws_iam_role_policy_attachment.node[*]: # worker, ecr, cni
  aws_eks_cluster.this:                     # needs: iam_role_policy_attachment.cluster, private subnets
                                            # authentication_mode API · creator admin permissions ON
    aws_eks_access_entry.this[*]:           # gate: var.access_entries
      aws_eks_access_policy_association.this[*]:
    aws_eks_addon.this[*]:                  # eks-pod-identity-agent, aws-ebs-csi-driver
  module.nodegroup:
    aws_eks_node_group.this[*]:             # ignore_changes on desired_size

module.pod_identity_ebs_csi:                # ns kube-system
  aws_iam_role.this + aws_iam_role_policy_attachment.managed + aws_eks_pod_identity_association.this
module.pod_identity_eso:                    # ns external-secrets · inline secretsmanager read
  aws_iam_role.this + aws_iam_role_policy.this + aws_eks_pod_identity_association.this
module.pod_identity_crossplane:             # ns crossplane-system · inline sts:AssumeRole per target account
  aws_iam_role.this + aws_iam_role_policy.this + aws_eks_pod_identity_association.this

module.external_secrets[0]:                 # helm_release · needs: nodegroup, pod_identity_eso
                                            # the association MUST precede the release, or CrashLoop
  module.argo_cd[0]:                        # helm_release · needs: external_secrets
module.crossplane[0]:                       # helm_release · needs: nodegroup, pod_identity_crossplane
  kubernetes_config_map_v1.platform_bootstrap:    # ns crossplane-system · the Terraform → GitOps contract

outputs:
  cluster_name:
  region:
  argocd_namespace:
  eso_namespace:
  crossplane_namespace:
  kubeconfig_command:
```

**Definitions:** [aws_ec2_transit_gateway_vpc_attachment_accepter](2026-08-27-resource-dictionary/aws_ec2_transit_gateway_vpc_attachment_accepter.md) · [aws_ec2_transit_gateway_route_table_propagation](2026-08-27-resource-dictionary/aws_ec2_transit_gateway_route_table_propagation.md) · [aws_iam_role](2026-08-27-resource-dictionary/aws_iam_role.md) · [aws_iam_role_policy_attachment](2026-08-27-resource-dictionary/aws_iam_role_policy_attachment.md) · [aws_iam_role_policy](2026-08-27-resource-dictionary/aws_iam_role_policy.md) · [aws_eks_cluster](2026-08-27-resource-dictionary/aws_eks_cluster.md) · [aws_eks_access_entry](2026-08-27-resource-dictionary/aws_eks_access_entry.md) · [aws_eks_access_policy_association](2026-08-27-resource-dictionary/aws_eks_access_policy_association.md) · [aws_eks_addon](2026-08-27-resource-dictionary/aws_eks_addon.md) · [aws_eks_node_group](2026-08-27-resource-dictionary/aws_eks_node_group.md) · [aws_eks_pod_identity_association](2026-08-27-resource-dictionary/aws_eks_pod_identity_association.md) · [helm_release](2026-08-27-resource-dictionary/helm_release.md) · [kubernetes_config_map_v1](2026-08-27-resource-dictionary/kubernetes_config_map_v1.md)

## 06 · private DNS and closing the endpoint  📋

Steps `2.4` and `2.5`. TGW delivers IP routing, not name resolution: the EKS API's private hosted
zone has to be reachable from the hub before the public endpoint can be switched off. Which root
owns these is **undecided**.

```yaml
private-hosted-zone-association:  # associate the cluster API's private zone with the hub VPC (free)
                                  # risk: the zone is not an aws_eks_cluster output and is recreated
                                  # per provision · plan B: Resolver inbound endpoint, ~US$ 0.25/h
  client-vpn-dns-servers:         # push the hub resolver (VPC base + 2) to the endpoint
    eks-endpoint-public-access:    # → false · acceptance: a full apply succeeds with the VPN connected
```

**Definitions:** [aws_route53_zone_association](2026-08-27-resource-dictionary/aws_route53_zone_association.md) · [aws_route53_resolver_endpoint](2026-08-27-resource-dictionary/aws_route53_resolver_endpoint.md)

## 07 · ingress — ALB at the hub, NLB in the spoke  📋

Phase 3. Variant B was chosen: nothing crosses accounts at runtime, and publishing a new app costs
zero AWS resources. The NLB is Terraform's, and `istio-ingressgateway` becomes a `ClusterIP` bound to
the target group — if the load balancer controller created the NLB, its ARN would only exist after
the workload, breaking the single apply.

```yaml
# 3.1 · spoke side (state: control-plane)
module.pod_identity_lbc:          # the 4th Pod Identity role
  aws_lb.internal:                # type network · fixed IPs via subnet_mapping cidrhost(...)
    aws_lb_target_group.istio:    # target_type ip
      # → ingressTargetGroupArn added to the platform-bootstrap ConfigMap

# 3.2 · hub side (state: control-plane, provider aws.network — lifecycle follows the cluster)
aws_acm_certificate.cluster_wildcard:       # *.<id>.<subzone>
  aws_route53_record.cluster_validation:
    aws_acm_certificate_validation.cluster:
      aws_lb_listener_certificate.cluster:  # attached to the shared ALB · SNI · quota 25 certs/ALB
aws_lb_target_group.spoke:        # the NLB's fixed private IPs
  aws_lb_listener_rule.spoke:     # host-header → this target group

# cluster side · the GitOps repo, not this one, not Terraform
istio-ingressgateway-service:     # ClusterIP, NOT LoadBalancer
  target-group-binding:           # needs: aws_lb_target_group.istio, the load balancer controller
    istio-gateway:
      virtual-service:            # → publishing an app is only this
```

**Definitions:** [aws_lb](2026-08-27-resource-dictionary/aws_lb.md) · [aws_lb_target_group](2026-08-27-resource-dictionary/aws_lb_target_group.md) · [aws_lb_listener_rule](2026-08-27-resource-dictionary/aws_lb_listener_rule.md) · [aws_lb_listener_certificate](2026-08-27-resource-dictionary/aws_lb_listener_certificate.md) · [target-group-binding](2026-08-27-resource-dictionary/target-group-binding.md) · [istio-ingressgateway-service](2026-08-27-resource-dictionary/istio-ingressgateway-service.md)

## 08 · isolation proofs  📋

Phase 4, no code yet. `4.1` adds a second minimal spoke (VPC plus a tiny instance, no cluster) and a
per-client group with its own Client VPN authorization rule, proving a person in group A reaches only
spoke A and that removing them from the group revokes it. `4.2` adds `azure/terraform/simulated-client/`
— an Azure VPN Gateway (active-active, BGP) and a per-client TGW route table — proving a whole client
network reaches only its own spoke, with a negative check on the TGW route tables.

---

## Fidelity notes

- **Cross-layer reads are data sources filtered by tag, never `terraform_remote_state`.** Deliberate:
  the reading side survives a backend or key change on the writing side. The filter must return
  exactly one id, and `scripts/generate-tfvars` checks that before the apply.
- **The state boundary follows the lifecycle, not the account.** A hub-account resource whose life is
  a spoke's — the tenant TGW route table, the cluster certificate, the target group, the listener
  rule — lives in the spoke's state via an aliased provider. Destroying the cell takes it along, with
  no orphan on the hub side.
- **A cross-account TGW attachment has two gates**, and both are easy to miss: org-wide RAM sharing
  (layer 03, one-off) and the explicit `..._accepter` on the hub side (layer 05).
- **Pod Identity ordering is real, unlike in the Crossplane monolith.** The association must exist
  before the Helm release that consumes it, or the pod crash-loops on `AccessDenied`. The addon,
  however, is created alongside and blocks nothing.
- **The single `terraform apply` is the acceptance criterion**, not a convenience: no `-target`, no
  two-phase apply, even though layer 05 configures `kubernetes` and `helm` from resources it creates
  in the same run.
- **Layer 00 is not Terraform and cannot be.** Enabling Organizations, moving accounts between OUs and
  registering the SAML application are console or CLI steps. A missing approved region there surfaces
  as an SCP explicit-deny at the first `Create*` of any later layer, which reads like a code bug.

## Teardown = reverse order (08 → 01)

Layers 01, 02 and 03 are permanent and cost nothing: the state bucket, the hub VPCs (no NAT) and the
hosted zone stay up. `prevent_destroy` guards the bucket and the zone.

```yaml
07 → 06 → 05:                     # the cell · destroy leaves no orphan on the hub side
04:                               # ~10 min, dominated by the Client VPN network associations
03, 02, 01:                       # kept · permanent, zero recurring cost
```

Within layer 05, the order that matters: Helm releases before the node group (uninstall goes through
the API server), the node group before the VPC (egress must live until the pods are gone), and the
TGW attachment before `module.network`.
