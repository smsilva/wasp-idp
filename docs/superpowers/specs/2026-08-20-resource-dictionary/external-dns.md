# external-dns

|  |  |
|---|---|
| **Description** | Controller that syncs DNS records in Route53 automatically from annotated Services/Ingress.<br><br>Installed via Helm, with write access to Route53 via Pod Identity.<br><br>Keeps the subzone names pointing to the right endpoints without manual record management. |
| **Provider** | provider-helm (+ IAM/Pod Identity) |
| **Kind** | Release |
| **Layer** | 05 · platform |
| **Dependencies** | `provider-configs/helm` (gate: alb ready, zoneId) |
| **Identity** | role + association + policy-route53 |
