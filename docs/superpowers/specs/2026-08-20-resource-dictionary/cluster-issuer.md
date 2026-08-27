# cluster-issuer

|  |  |
|---|---|
| **Description** | `ClusterIssuer` from cert-manager configured for ACME (Let's Encrypt) with DNS-01 challenge on Route53.<br><br>Defines *how* certificates are issued cluster-wide; `certificate-wildcard` references it.<br><br>Needs the subzone's `zoneId` to know where to create the validation records. |
| **Provider** | provider-kubernetes |
| **Kind** | Object (ClusterIssuer) |
| **Layer** | 06 · objects |
| **Dependencies** | `cert-manager` (gate: zoneId) |
