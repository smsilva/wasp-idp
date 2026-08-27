# eks-node-role

|  |  |
|---|---|
| **Description** | IAM role that the nodes' EC2 instances assume (trust on `ec2.amazonaws.com`).<br><br>Gets its permissions from the `node-policies` (worker, ECR, CNI).<br><br>Prerequisite of `eks-node-group`. |
| **Provider** | provider-aws-iam |
| **Kind** | Role |
| **Layer** | 02 · iam |
| **Dependencies** | None |
