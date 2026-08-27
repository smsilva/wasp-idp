# Resource dictionary — this repository

Every resource this repository provisions, from account bootstrap to the spoke. Companion of
[`2026-08-27-provisioning-sequence.md`](2026-08-27-provisioning-sequence.md).

For the Crossplane monolith of the corporate trail — a different, narrower set — see
[`2026-08-20-resource-dictionary.md`](2026-08-20-resource-dictionary.md).

**Layer** is the layer of the sequence document. **State** is which Terraform state owns the resource
(`—` when it is not Terraform's). Ordered by layer, then alphabetically. Each **Resource** links to
its own file in [`2026-08-27-resource-dictionary/`](2026-08-27-resource-dictionary/).

| Layer | Resource | Type | State | Description |
|---|---|---|---|---|
| 00 · accounts | [**baseline-scps**](2026-08-27-resource-dictionary/baseline-scps.md) | Service Control Policy ×5 | — | Guardrails on Root and each OU: no leaving the org, no touching the trail, approved regions only, IMDSv2, no root user. |
| 00 · accounts | [**identity-center**](2026-08-27-resource-dictionary/identity-center.md) | IAM Identity Center instance + permission sets | — | Interactive human access, granted to groups rather than users. |
| 00 · accounts | [**log-archive-bucket**](2026-08-27-resource-dictionary/log-archive-bucket.md) | S3 bucket | — | Destination of the organization trail, in its own account so no audited admin can delete their own logs. |
| 00 · accounts | [**organization**](2026-08-27-resource-dictionary/organization.md) | AWS Organizations org | — | Feature set `ALL`; without it SCPs do not work at all. |
| 00 · accounts | [**organization-account-access-role**](2026-08-27-resource-dictionary/organization-account-access-role.md) | IAM Role | — | Auto-created in every member account; the bootstrap path until a permission set exists. |
| 00 · accounts | [**organization-trail**](2026-08-27-resource-dictionary/organization-trail.md) | CloudTrail trail | — | Multi-region org-wide trail with log-file validation, created before any other account. |
| 00 · accounts | [**ou-structure**](2026-08-27-resource-dictionary/ou-structure.md) | Organizational Unit ×5 | — | `Security`, `Infrastructure`, `Deployments`, `Workloads/NonProd`, `Workloads/Production`. |
| 00 · accounts | [**saml-application**](2026-08-27-resource-dictionary/saml-application.md) | Identity Center application | — | Console-only artifact whose metadata XML the Client VPN federation consumes. |
| 01 · state-backend | [**aws_s3_bucket**](2026-08-27-resource-dictionary/aws_s3_bucket.md) | S3 bucket | state-backend | Holds every layer's state, including its own. `prevent_destroy`. |
| 01 · state-backend | [**aws_s3_bucket_ownership_controls**](2026-08-27-resource-dictionary/aws_s3_bucket_ownership_controls.md) | S3 ownership controls | state-backend | `BucketOwnerEnforced` — disables ACLs entirely. |
| 01 · state-backend | [**aws_s3_bucket_policy**](2026-08-27-resource-dictionary/aws_s3_bucket_policy.md) | S3 bucket policy | state-backend | Denies non-TLS access; must be applied after the public-access block. |
| 01 · state-backend | [**aws_s3_bucket_public_access_block**](2026-08-27-resource-dictionary/aws_s3_bucket_public_access_block.md) | S3 public access block | state-backend | All four blocks on. |
| 01 · state-backend | [**aws_s3_bucket_server_side_encryption_configuration**](2026-08-27-resource-dictionary/aws_s3_bucket_server_side_encryption_configuration.md) | S3 SSE config | state-backend | SSE-S3 at rest. |
| 01 · state-backend | [**aws_s3_bucket_versioning**](2026-08-27-resource-dictionary/aws_s3_bucket_versioning.md) | S3 versioning | state-backend | Version history of the state — the recovery path after a bad apply. |
| 02 · network-foundation | [**aws_eip**](2026-08-27-resource-dictionary/aws_eip.md) | EIP | network-foundation / control-plane | Fixed public IP for the NAT gateway. Not created in the hub. |
| 02 · network-foundation | [**aws_internet_gateway**](2026-08-27-resource-dictionary/aws_internet_gateway.md) | InternetGateway | network-foundation / control-plane | The VPC's door to the internet. |
| 02 · network-foundation | [**aws_nat_gateway**](2026-08-27-resource-dictionary/aws_nat_gateway.md) | NATGateway | network-foundation / control-plane | Egress for the private subnets. Gated off in the hub — nothing routes there yet and it would bill ~US$ 32/month for zero traffic. |
| 02 · network-foundation | [**aws_route**](2026-08-27-resource-dictionary/aws_route.md) | Route | network-foundation / connectivity / control-plane | Individual route: default to the internet, or the supernet to the transit gateway. |
| 02 · network-foundation | [**aws_route_table**](2026-08-27-resource-dictionary/aws_route_table.md) | RouteTable ×2 | network-foundation / control-plane | `public` and `private` tables of a VPC. |
| 02 · network-foundation | [**aws_route_table_association**](2026-08-27-resource-dictionary/aws_route_table_association.md) | RouteTableAssociation ×4 | network-foundation / control-plane | Binds each subnet to its table. |
| 02 · network-foundation | [**aws_subnet**](2026-08-27-resource-dictionary/aws_subnet.md) | Subnet ×4 | network-foundation / control-plane | Two public and two private `/20`s, one pair per AZ. |
| 02 · network-foundation | [**aws_vpc**](2026-08-27-resource-dictionary/aws_vpc.md) | VPC | network-foundation / control-plane | A `/16` out of the `10.0.0.0/12` supernet — the only irreversible decision in the chain. |
| 03 · dns | [**aws_ram_sharing_with_organization**](2026-08-27-resource-dictionary/aws_ram_sharing_with_organization.md) | RAM org sharing | dns | Org-wide toggle, permanent, first of the two gates any cross-account TGW attachment needs. |
| 03 · dns | [**aws_route53_zone**](2026-08-27-resource-dictionary/aws_route53_zone.md) | Route 53 Zone | dns | The delegated nonprod subzone; every cluster and app name hangs off it. `prevent_destroy`. |
| 03 · dns | [**azurerm_dns_ns_record**](2026-08-27-resource-dictionary/azurerm_dns_ns_record.md) | Azure DNS NS record | dns | The delegation in the parent zone, which lives in Azure DNS. |
| 04 · connectivity | [**aws_acm_certificate**](2026-08-27-resource-dictionary/aws_acm_certificate.md) | ACM Certificate | connectivity / control-plane | Public certificate for the VPN endpoint, and later the cluster wildcard. `create_before_destroy`. |
| 04 · connectivity | [**aws_acm_certificate_validation**](2026-08-27-resource-dictionary/aws_acm_certificate_validation.md) | ACM validation | connectivity / control-plane | Blocks until the certificate is issued; ~1 s once the record exists. |
| 04 · connectivity | [**aws_ec2_client_vpn_authorization_rule**](2026-08-27-resource-dictionary/aws_ec2_client_vpn_authorization_rule.md) | Client VPN authorization rule | connectivity | One per group and destination CIDR — where per-client isolation is actually enforced. |
| 04 · connectivity | [**aws_ec2_client_vpn_endpoint**](2026-08-27-resource-dictionary/aws_ec2_client_vpn_endpoint.md) | Client VPN endpoint | connectivity | The maintenance tunnel, federated through SAML. It performs SNAT — traffic reaches the spoke with a hub-VPC source IP. |
| 04 · connectivity | [**aws_ec2_client_vpn_network_association**](2026-08-27-resource-dictionary/aws_ec2_client_vpn_network_association.md) | Client VPN network association | connectivity | One per hub private subnet. ~7–10 min each, in both directions — the reason a teardown takes over 10 min. |
| 04 · connectivity | [**aws_ec2_client_vpn_route**](2026-08-27-resource-dictionary/aws_ec2_client_vpn_route.md) | Client VPN route | connectivity | Pushes the supernet to the client; needs an explicit `depends_on` its own subnet's association. |
| 04 · connectivity | [**aws_ec2_transit_gateway**](2026-08-27-resource-dictionary/aws_ec2_transit_gateway.md) | Transit Gateway | connectivity | The single crossroads. Default association and propagation both disabled, so isolation is the default. |
| 04 · connectivity | [**aws_ec2_transit_gateway_route_table**](2026-08-27-resource-dictionary/aws_ec2_transit_gateway_route_table.md) | TGW route table | connectivity / control-plane | One for the hub, one per tenant — the tenant table isolates in both directions without a security group. |
| 04 · connectivity | [**aws_ec2_transit_gateway_route_table_association**](2026-08-27-resource-dictionary/aws_ec2_transit_gateway_route_table_association.md) | TGW route table association | connectivity / control-plane | Which table an attachment consults when sending. |
| 04 · connectivity | [**aws_ec2_transit_gateway_vpc_attachment**](2026-08-27-resource-dictionary/aws_ec2_transit_gateway_vpc_attachment.md) | TGW VPC attachment | connectivity / control-plane | Plugs a VPC into the TGW. Needs `ignore_changes` on the default association and propagation flags, or it diffs forever. |
| 04 · connectivity | [**aws_iam_saml_provider**](2026-08-27-resource-dictionary/aws_iam_saml_provider.md) | IAM SAML provider | connectivity | Registers the Identity Center metadata so the VPN can federate. |
| 04 · connectivity | [**aws_ram_principal_association**](2026-08-27-resource-dictionary/aws_ram_principal_association.md) | RAM principal association | connectivity | One per spoke account allowed to attach. |
| 04 · connectivity | [**aws_ram_resource_association**](2026-08-27-resource-dictionary/aws_ram_resource_association.md) | RAM resource association | connectivity | Puts the transit gateway into the share. |
| 04 · connectivity | [**aws_ram_resource_share**](2026-08-27-resource-dictionary/aws_ram_resource_share.md) | RAM resource share | connectivity | The share through which spoke accounts see the TGW. |
| 04 · connectivity | [**aws_route53_record**](2026-08-27-resource-dictionary/aws_route53_record.md) | Route 53 Record | connectivity / control-plane | DNS validation record for a certificate, in the subzone. |
| 05 · control-plane | [**aws_ec2_transit_gateway_route_table_propagation**](2026-08-27-resource-dictionary/aws_ec2_transit_gateway_route_table_propagation.md) | TGW route propagation ×2 | control-plane | Advertises each side's CIDR into the other's table. The two are not symmetric — swapping their arguments silently breaks routing. |
| 05 · control-plane | [**aws_ec2_transit_gateway_vpc_attachment_accepter**](2026-08-27-resource-dictionary/aws_ec2_transit_gateway_vpc_attachment_accepter.md) | TGW attachment accepter | control-plane | The hub-side acceptance, via aliased provider — the second gate of a cross-account attachment. |
| 05 · control-plane | [**aws_eks_access_entry**](2026-08-27-resource-dictionary/aws_eks_access_entry.md) | EKS access entry | control-plane | Registers an IAM principal with the cluster API. Replaces `aws-auth`. |
| 05 · control-plane | [**aws_eks_access_policy_association**](2026-08-27-resource-dictionary/aws_eks_access_policy_association.md) | EKS access policy association | control-plane | Grants an access entry its EKS-managed policy; the API demands the entry first. |
| 05 · control-plane | [**aws_eks_addon**](2026-08-27-resource-dictionary/aws_eks_addon.md) | EKS Addon ×2 | control-plane | `eks-pod-identity-agent` and `aws-ebs-csi-driver`. |
| 05 · control-plane | [**aws_eks_cluster**](2026-08-27-resource-dictionary/aws_eks_cluster.md) | EKS Cluster | control-plane | The managed control plane, `authentication_mode = API`, in the private subnets. |
| 05 · control-plane | [**aws_eks_node_group**](2026-08-27-resource-dictionary/aws_eks_node_group.md) | EKS NodeGroup | control-plane | Managed node pool. `ignore_changes` on `desired_size` so the autoscaler is not fought. |
| 05 · control-plane | [**aws_eks_pod_identity_association**](2026-08-27-resource-dictionary/aws_eks_pod_identity_association.md) | Pod Identity association | control-plane | Binds a namespace and ServiceAccount to an IAM role — no OIDC, no IRSA annotations. Must exist before the workload. |
| 05 · control-plane | [**aws_iam_role**](2026-08-27-resource-dictionary/aws_iam_role.md) | IAM Role | control-plane | Cluster role, node role, and one per Pod Identity consumer. |
| 05 · control-plane | [**aws_iam_role_policy**](2026-08-27-resource-dictionary/aws_iam_role_policy.md) | IAM inline policy | control-plane | Inline grants: Secrets Manager reads for the secrets operator, `sts:AssumeRole` into target accounts for Crossplane. |
| 05 · control-plane | [**aws_iam_role_policy_attachment**](2026-08-27-resource-dictionary/aws_iam_role_policy_attachment.md) | IAM managed policy attachment | control-plane | AWS-managed policies on the cluster, node and CSI roles. |
| 05 · control-plane | [**helm_release**](2026-08-27-resource-dictionary/helm_release.md) | Helm Release ×3 | control-plane | External Secrets, Argo CD and Crossplane, installed in the same apply that created the cluster. |
| 05 · control-plane | [**kubernetes_config_map_v1**](2026-08-27-resource-dictionary/kubernetes_config_map_v1.md) | ConfigMap | control-plane | `platform-bootstrap` — the contract Terraform hands to GitOps. |
| 06 · private DNS | [**aws_route53_resolver_endpoint**](2026-08-27-resource-dictionary/aws_route53_resolver_endpoint.md) | Resolver inbound endpoint | undecided | Plan B for resolving the cluster API from the hub, at ~US$ 0.25/h. |
| 06 · private DNS | [**aws_route53_zone_association**](2026-08-27-resource-dictionary/aws_route53_zone_association.md) | Zone/VPC association | undecided | Free plan A: associate the cluster API's private zone with the hub VPC. The zone is not an EKS output and is recreated per provision. |
| 07 · ingress | [**aws_lb**](2026-08-27-resource-dictionary/aws_lb.md) | Network Load Balancer | control-plane | Internal NLB in the spoke, with fixed private IPs so the hub can target it without an ENI lookup. |
| 07 · ingress | [**aws_lb_listener_certificate**](2026-08-27-resource-dictionary/aws_lb_listener_certificate.md) | ALB listener certificate | control-plane (hub provider) | Attaches the cluster wildcard to the shared listener by SNI. The 25-certificates-per-ALB quota is the limit on cells. |
| 07 · ingress | [**aws_lb_listener_rule**](2026-08-27-resource-dictionary/aws_lb_listener_rule.md) | ALB listener rule | control-plane (hub provider) | Host-header match sending a cell's traffic to its target group. |
| 07 · ingress | [**aws_lb_target_group**](2026-08-27-resource-dictionary/aws_lb_target_group.md) | Target group ×2 | control-plane | `type = ip`: one the gateway pods register into, one holding the NLB's IPs for the ALB. |
| 07 · ingress | [**istio-ingressgateway-service**](2026-08-27-resource-dictionary/istio-ingressgateway-service.md) | Service (ClusterIP) | — (GitOps) | `ClusterIP`, never `LoadBalancer` — the NLB is Terraform's, so its ARN exists before any workload. |
| 07 · ingress | [**target-group-binding**](2026-08-27-resource-dictionary/target-group-binding.md) | TargetGroupBinding | — (GitOps) | Registers the gateway pods into the Terraform-created target group. One NLB per cluster, not per Service. |
