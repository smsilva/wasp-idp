# aws-load-balancer-controller

|  |  |
|---|---|
| **Description** | Controller that translates Kubernetes `LoadBalancer` Services (and Ingress) into real NLBs/ALBs on AWS.<br><br>Installed via Helm, with IAM permission delivered through Pod Identity. In the echo walkthrough, it is the one that materializes the NLB from the `istio-ingress-gateway` Service.<br><br>It is also the one that deletes the NLB during teardown — that is why it needs live creds until the gateway is gone. |
| **Provider** | provider-helm (+ IAM/Pod Identity) |
| **Kind** | Release |
| **Layer** | 05 · platform |
| **Dependencies** | `provider-configs/helm`, `vpcId` (gate: vpcId) |
| **Identity** | role + policy + association (Pod Identity) |
| **Teardown** | held by `istio-ingress-gateway` (cleans up the NLB before it goes) |
