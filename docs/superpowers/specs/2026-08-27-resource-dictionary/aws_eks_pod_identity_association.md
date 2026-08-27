# aws_eks_pod_identity_association

|  |  |
|---|---|
| **Description** | Binds a `(namespace, service account)` pair to an IAM role via EKS Pod Identity — no OIDC provider, no IRSA annotations. One per Pod Identity module instance: EBS CSI driver, External Secrets, Crossplane (and later the load balancer controller). |
| **Provider** | `terraform · aws` |
| **Type** | `Pod Identity association` |
| **Layer** | `05 · control-plane` |
| **State** | `control-plane` |
| **Dependencies** | `var.cluster_name` (`module.cluster`), `aws_iam_role.this` (same module instance) |
| **Produces** | The credential-delivery binding a Helm release's pods rely on at runtime; `module.pod_identity_eso`/`module.pod_identity_crossplane` are named in the `depends_on` of `module.external_secrets`/`module.crossplane` |
| **Teardown** | Removed after the workload that consumes it is uninstalled; removing it first strands the pods with no credentials, though they keep running until restarted |

## Examples

- The association MUST exist before the Helm release that consumes it, or the pod crash-loops on `AccessDenied` — enforced here via explicit `depends_on` from `module.external_secrets`/`module.crossplane`/`module.argo_cd` (transitively) onto the corresponding `module.pod_identity_*`.
- The trust policy on the associated role needs both `sts:AssumeRole` and `sts:TagSession`; a trust with only `AssumeRole` produces an `AccessDenied` that does not point at the missing action.
- The EBS CSI Pod Identity role has no inline policy — only the managed `AmazonEBSCSIDriverPolicy` attachment — while External Secrets and Crossplane each carry a purpose-built inline policy instead.
