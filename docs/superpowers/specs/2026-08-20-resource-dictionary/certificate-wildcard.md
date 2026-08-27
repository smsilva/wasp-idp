# certificate-wildcard

|  |  |
|---|---|
| **Description** | `Certificate` resource that makes cert-manager issue the wildcard cert `*.<zone>` and store it in a TLS Secret used by the Istio gateway.<br><br>A single cert covers every host in the subzone (echo and future apps).<br><br>Depends on the `cluster-issuer` (the ACME issuer) already being ready. |
| **Provider** | provider-kubernetes |
| **Kind** | Object (Certificate) |
| **Layer** | 06 · objects |
| **Dependencies** | `cluster-issuer`, `cert-manager` |
