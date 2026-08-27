# nlb-hostname-observer

|  |  |
|---|---|
| **Description** | Object in Observe-only mode that just reads (does not create) the hostname of the NLB provisioned by the istio-ingress-gateway's Service.<br><br>Acts as a bridge: exposes the NLB hostname so the DNS layer can build the wildcard record.<br><br>Since the NLB only gets a hostname after it is created, this observer tends to take a while to resolve — force a re-poll with a `kubectl annotate` on the Object. |
| **Provider** | provider-kubernetes |
| **Kind** | Object (Observe) |
| **Layer** | 04 · dns |
| **Dependencies** | `provider-configs/kubernetes` (observes `istio-ingress-gateway`) |
