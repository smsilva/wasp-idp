# Resource dictionary — Environment (monolith)

Resources provisioned by the `environment-eks` Composition, as it stands in the corporate
trail. Companion of
[`2026-08-20-provisioning-sequence.md`](2026-08-20-provisioning-sequence.md).

Provider (column): `ec2 · eks · iam · route53` = `provider-aws-*`; `helm` = provider-helm;
`kubernetes` = provider-kubernetes. Ordered by provider, then alphabetically. Each **Resource**
links to its own file in [`2026-08-20-resource-dictionary/`](2026-08-20-resource-dictionary/).

| Provider | Resource | Kind | Description |
|---|---|---|---|
| ec2 | [**associations**](2026-08-20-resource-dictionary/associations.md) | RouteTableAssociation ×4 | Link each subnet to its route table. |
| ec2 | [**internet-gateway**](2026-08-20-resource-dictionary/internet-gateway.md) | InternetGateway | The VPC's door to the internet (public ingress/egress). |
| ec2 | [**nat-elastic-ip**](2026-08-20-resource-dictionary/nat-elastic-ip.md) | EIP | Fixed public IP allocated to the NAT Gateway. |
| ec2 | [**nat-gateway**](2026-08-20-resource-dictionary/nat-gateway.md) | NATGateway | Gives internet egress to the private subnets; lives in a public subnet. |
| ec2 | [**route-default**](2026-08-20-resource-dictionary/route-default.md) | Route | Default route `0.0.0.0/0` from a route table to its gateway. |
| ec2 | [**route-tables**](2026-08-20-resource-dictionary/route-tables.md) | RouteTable ×2 | Route tables: `public` (→ internet-gateway) and `private` (→ nat-gateway). |
| ec2 | [**subnets**](2026-08-20-resource-dictionary/subnets.md) | Subnet ×4 | Subnets per AZ (`us-east-1a/1b`): `public-*` (public IP) and `private-*` (nodes/pods). |
| ec2 | [**vpc**](2026-08-20-resource-dictionary/vpc.md) | VPC | Isolated network (CIDR `172.16.0.0/16`) where the whole cluster lives. |
| eks | [**access-entry-crossplane**](2026-08-20-resource-dictionary/access-entry-crossplane.md) | AccessEntry | Registers Crossplane's IAM (`crossplaneArn`) with the cluster API. |
| eks | [**access-policy-crossplane**](2026-08-20-resource-dictionary/access-policy-crossplane.md) | AccessPolicyAssociation | Grants Crossplane the `AmazonEKSClusterAdminPolicy`. |
| eks | [**addon-pod-identity-agent**](2026-08-20-resource-dictionary/addon-pod-identity-agent.md) | Addon | `eks-pod-identity-agent`; delivers AWS credentials to pods (Pod Identity). |
| eks | [**cluster-auth**](2026-08-20-resource-dictionary/cluster-auth.md) | ClusterAuth | Generates the kubeconfig and publishes it to the `<full>-kubeconfig` Secret. |
| eks | [**ebs-csi-driver**](2026-08-20-resource-dictionary/ebs-csi-driver.md) | Addon + PodIdentityAssociation (+ iam Role/RolePolicyAttachment) | EBS volume driver (role + policy + association + addon). |
| eks | [**eks-cluster**](2026-08-20-resource-dictionary/eks-cluster.md) | Cluster | EKS managed control plane (v1.34); uses the 4 subnets. |
| eks | [**eks-node-group**](2026-08-20-resource-dictionary/eks-node-group.md) | NodeGroup | Managed node pool (EC2 t3.medium) in the private subnets. |
| iam | [**eks-cluster-policy**](2026-08-20-resource-dictionary/eks-cluster-policy.md) | RolePolicyAttachment | Attaches `AmazonEKSClusterPolicy` to the eks-cluster-role. |
| iam | [**eks-cluster-role**](2026-08-20-resource-dictionary/eks-cluster-role.md) | Role | Role assumed by the EKS control plane. |
| iam | [**eks-node-role**](2026-08-20-resource-dictionary/eks-node-role.md) | Role | Role assumed by the cluster's EC2 nodes. |
| iam | [**node-policies**](2026-08-20-resource-dictionary/node-policies.md) | RolePolicyAttachment ×3 | `worker`, `ecr`, `cni` on the eks-node-role. |
| route53 | [**records**](2026-08-20-resource-dictionary/records.md) | Record ×2 | `delegation` (NS on the parent zone) and `wildcard` (`*.<zone>` A-alias → NLB). |
| route53 | [**route53-hosted-zone**](2026-08-20-resource-dictionary/route53-hosted-zone.md) | Zone | DNS subzone `<name>.<domainSuffix>` dedicated to the cluster (`forceDestroy`). |
| helm | [**aws-load-balancer-controller**](2026-08-20-resource-dictionary/aws-load-balancer-controller.md) | Release (+ IAM/Pod Identity) | Creates/manages the NLB from the gateway's Service LoadBalancer. |
| helm | [**cert-manager**](2026-08-20-resource-dictionary/cert-manager.md) | Release (+ IAM/Pod Identity) | Issues/renews TLS certificates via ACME DNS-01 (Let's Encrypt) on Route53. |
| helm | [**external-dns**](2026-08-20-resource-dictionary/external-dns.md) | Release (+ IAM/Pod Identity) | Syncs DNS records on Route53 based on Services/Ingress. |
| helm | [**istio-base**](2026-08-20-resource-dictionary/istio-base.md) | Release | Istio's base CRDs and resources. |
| helm | [**istio-ingress-gateway**](2026-08-20-resource-dictionary/istio-ingress-gateway.md) | Release | Istio's ingress gateway; creates the Service LoadBalancer that becomes the NLB. |
| helm | [**istiod**](2026-08-20-resource-dictionary/istiod.md) | Release | Istio's control plane (injects the sidecar and the gateway's proxy image). |
| helm | [**provider-configs**](2026-08-20-resource-dictionary/provider-configs.md) | ProviderConfig ×2 (helm + kubernetes) | Remote PCs pointing at the spoke via the Secret-kubeconfig. |
| kubernetes | [**certificate-wildcard**](2026-08-20-resource-dictionary/certificate-wildcard.md) | Object (Certificate) | Certificate `*.<zone>` (wildcard TLS Secret) for the gateway. |
| kubernetes | [**cluster-issuer**](2026-08-20-resource-dictionary/cluster-issuer.md) | Object (ClusterIssuer) | ACME issuer (Let's Encrypt DNS-01) used by cert-manager. |
| kubernetes | [**echo**](2026-08-20-resource-dictionary/echo.md) | Object ×5 | Validation app (httpbin): namespace, deployment, service, gateway and virtualservice. |
| kubernetes | [**nlb-hostname-observer**](2026-08-20-resource-dictionary/nlb-hostname-observer.md) | Object (Observe) | Reads the NLB hostname from the gateway's Service (feeds the wildcard). |
