# istiod

|  |  |
|---|---|
| **Description** | Istio control plane: distributes config to the proxies, injects the Envoy sidecar, and provides the gateway proxy image.<br><br>Depends on the `istio-base` CRDs.<br><br>It is a prerequisite for `istio-ingress-gateway` — without istiod ready, the gateway gets no config or proxy. |
| **Provider** | provider-helm |
| **Kind** | Release |
| **Layer** | 05 · platform |
| **Dependencies** | `istio-base` (gate: alb ready + istio-base ready) |
