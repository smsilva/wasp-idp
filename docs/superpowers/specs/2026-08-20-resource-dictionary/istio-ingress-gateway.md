# istio-ingress-gateway

|  |  |
|---|---|
| **Description** | Istio ingress gateway: creates a `LoadBalancer` Service that the aws-load-balancer-controller materializes as an NLB.<br><br>It is the cluster's HTTP(S) entry point — terminates TLS with the wildcard cert and routes via `VirtualService`. Its NLB hostname is read by `nlb-hostname-observer` to build the wildcard DNS.<br><br>On teardown it goes before the controller, so the NLB is removed first. |
| **Provider** | provider-helm |
| **Kind** | Release |
| **Layer** | 05 · platform |
| **Dependencies** | `istiod` (gate: istiod ready) |
| **Produces** | the NLB (observed by `nlb-hostname-observer`) |
| **Teardown** | removed before `aws-load-balancer-controller` (the NLB goes first) |
