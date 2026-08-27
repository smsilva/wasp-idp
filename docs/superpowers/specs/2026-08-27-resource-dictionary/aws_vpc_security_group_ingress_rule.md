# aws_vpc_security_group_ingress_rule

|  |  |
|---|---|
| **Status** | `Written` — step `2.4`. Acceptance runs together with `2.5`, since only a closed public endpoint makes the private path observable. |
| **Description** | Allows `443/tcp` into the EKS **cluster** security group from the hub VPC CIDR. This is the whole of what step `2.4` turned out to be: the EKS documentation requires exactly this rule for a network connected by Transit Gateway, and requires nothing about DNS. |
| **Provider** | `terraform · aws` (default, the `cicd` account — the security group lives in the spoke VPC) |
| **Type** | `Security group rule` |
| **Layer** | `05 · control-plane` (documented under `06 · closing the endpoint`) |
| **State** | `control-plane/` |
| **Dependencies** | The cluster security group (computed by EKS, `module.cluster.cluster_security_group_id`) and `data.aws_vpc.hub` for the source CIDR |
| **Produces** | The only path to the Kubernetes API once the public endpoint is closed — used by the operator **and** by the `helm`/`kubernetes` providers during `terraform apply` |
| **Teardown** | Leaves with the cluster. The security group is EKS-managed and recreated per cluster, so the rule is recreated with it — unlike the temporary ICMP rule of step `2.3`, this one is not manual drift |

## Examples

- The documented requirement, for the *connected network* case: "You must ensure that your Amazon EKS control plane security group contains rules to allow ingress traffic on port 443 from your connected network."
- The source is the **hub VPC CIDR**, not the Client VPN client CIDR. The Client VPN performs SNAT, so an operator's packet arrives in the spoke with a hub address — proven with a real packet in step `2.3`, and the same reason this layer has no route for the client CIDR.
- The cluster security group is the right target because it is what governs the **private** endpoint. `public_access_cidrs` governs only the public one, and the two controls never overlap: "the public access CIDRs don't affect the private endpoint."
- **Ordering is real, and invisible to `terraform test`.** The rule must exist before any `helm`/`kubernetes` resource, because it opens the path those providers use to reach the API server. The edge is an explicit `depends_on` on the helm modules and the ConfigMap; nothing in the provider configuration creates it. Without the edge the symptom is a timeout on the first release, far from the cause.
- Tested with **two** `override_data` values for `data.aws_vpc.hub` (`10.1.0.0/16` and `10.7.0.0/16`). One override would only prove the value: a CIDR hardcoded in the configuration would pass — the trap confirmed in step `1.3`.
