# addon-pod-identity-agent

|  |  |
|---|---|
| **Description** | `eks-pod-identity-agent` addon: runs an agent on every node that injects temporary AWS credentials into pods according to the `PodIdentityAssociation`s.<br><br>It is the mechanism that replaces IRSA/OIDC — every association (ebs-csi, alb, external-dns, cert-manager) depends on it at runtime.<br><br>That is why it is among the last to go during teardown: the alb-controller still needs live creds to delete the NLB. |
| **Provider** | provider-aws-eks |
| **Kind** | Addon |
| **Layer** | 03 · eks |
| **Dependencies** | `eks-cluster` |
| **Teardown** | held by `aws-load-balancer-controller` (live creds to delete the NLB) |
