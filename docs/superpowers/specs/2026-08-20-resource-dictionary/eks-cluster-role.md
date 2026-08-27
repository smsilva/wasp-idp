# eks-cluster-role

|  |  |
|---|---|
| **Description** | IAM role that the EKS control plane assumes (trust on `eks.amazonaws.com`) to act in AWS on behalf of the cluster.<br><br>It's the control plane's identity; it gets its permissions from `eks-cluster-policy`.<br><br>Prerequisite to create the `eks-cluster`. |
| **Provider** | provider-aws-iam |
| **Kind** | Role |
| **Layer** | 02 · iam |
| **Dependencies** | None |
