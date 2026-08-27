# helm_release

|  |  |
|---|---|
| **Description** | The three charts installed straight from this root, in the same `terraform apply` that created the cluster: External Secrets Operator (`external-secrets/external-secrets`, `2.9.0`), Argo CD (`argo-helm/argo-cd`, `10.4.0`), and Crossplane core only (`charts.crossplane.io/stable`, `2.4.0` — providers/functions/ProviderConfigs arrive later via GitOps, not here). |
| **Provider** | `terraform · helm` |
| **Type** | `Helm Release ×3` |
| **Layer** | `05 · control-plane` |
| **State** | `control-plane` |
| **Dependencies** | External Secrets: `depends_on = [module.nodegroup, module.pod_identity_eso]`. Argo CD: `depends_on = [module.external_secrets]`. Crossplane: `depends_on = [module.nodegroup, module.pod_identity_crossplane]` |
| **Produces** | `namespace` (each) — consumed by root outputs (`eso_namespace`, `argocd_namespace`, `crossplane_namespace`); Crossplane's release is also a dependency of `kubernetes_config_map_v1.platform_bootstrap` |
| **Teardown** | Uninstalled through the API server before the node group is removed; the ArgoCD release leaves its CRDs (`applications`, `applicationsets`, `appprojects.argoproj.io`) behind on a release-only removal due to Helm's resource-policy keep annotation — harmless when the whole cluster goes with it |

## Examples

- Ordering is Pod Identity association → Helm release, never the other way — `module.external_secrets` and `module.crossplane` both list their Pod Identity module in `depends_on`, or the operator pod crash-loops on `AccessDenied`.
- Argo CD depends on External Secrets (not the other way around) because the ESO merges the OIDC client secret into the `argocd-secret` (`creationPolicy: Merge`) that Argo CD's OIDC config placeholder resolves against.
- The `kubernetes`/`helm` providers are configured from this same root's `module.cluster` outputs (`cluster_endpoint`, `cluster_ca_data`) — a single apply spans the `aws`, `kubernetes` and `helm` providers with no `-target`, which is the acceptance criterion for this layer, not a convenience.
- Crossplane's release installs only the core; providers, functions and `ProviderConfig`s are delivered by GitOps reading the `platform-bootstrap` ConfigMap this release's namespace hosts.
