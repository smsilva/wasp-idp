# cert-manager

|  |  |
|---|---|
| **Description** | Controller that issues and automatically renews TLS certificates via ACME DNS-01 (Let's Encrypt), proving domain ownership through Route53 records.<br><br>Installed via Helm, with write permission on Route53 through Pod Identity.<br><br>Feeds the `cluster-issuer` (the issuer) and the `certificate-wildcard` that protects the gateway. |
| **Provider** | provider-helm (+ IAM/Pod Identity) |
| **Kind** | Release |
| **Layer** | 05 · platform |
| **Dependencies** | `provider-configs/helm` (gate: alb ready) |
| **Identity** | role + association + policy-route53 |
