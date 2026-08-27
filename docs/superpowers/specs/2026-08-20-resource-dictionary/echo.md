# echo

|  |  |
|---|---|
| **Description** | End-to-end validation app (httpbin) exposed at `https://echo.<zone>`.<br><br>It's the proof that provisioning closed the loop: it covers namespace, deployment, service, Istio gateway (wildcard TLS), and virtualservice.<br><br>A GET on `/get` returning HTTP 200 confirms that network, cluster, DNS, TLS, and ingress are up and talking to each other. |
| **Provider** | provider-kubernetes |
| **Kind** | Object ×5 |
| **Layer** | 06 · objects |
| **Dependencies** | `istio-ingress-gateway`, `certificate-wildcard` |
| **Produces** | `https://echo.<zone>/get` → HTTP 200 |

## Examples

- `namespace` — `echo`
- `deployment` — httpbin (readiness `/status/200`)
- `service` — ClusterIP
- `gateway` — Istio (TLS SIMPLE, wildcard cert)
- `virtualservice` — routes the host → service (redirect 80→443)
