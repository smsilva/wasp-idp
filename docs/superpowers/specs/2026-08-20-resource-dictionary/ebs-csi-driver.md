# ebs-csi-driver

|  |  |
|---|---|
| **Description** | AWS CSI driver that lets the cluster provision EBS volumes for `PersistentVolumeClaim`s.<br><br>Installed as an EKS managed addon, with IAM permission (`AmazonEBSCSIDriverPolicy`) delivered via Pod Identity to the SA `ebs-csi-controller-sa`.<br><br>Without it, every PVC stays `Pending`. |
| **Provider** | provider-aws-eks (+ provider-aws-iam) |
| **Kind** | Addon + PodIdentityAssociation (+ Role/RolePolicyAttachment) |
| **Layer** | 03 · eks |
| **Dependencies** | `eks-cluster` (+ `addon-pod-identity-agent` at runtime) |

## Examples

- `role` — Pod Identity (trust `pods.eks.amazonaws.com`)
- `policy` — AmazonEBSCSIDriverPolicy
- `association` — SA `ebs-csi-controller-sa` (`kube-system`)
- `addon` — `aws-ebs-csi-driver`
