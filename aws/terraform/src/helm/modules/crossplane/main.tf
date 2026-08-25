# Somente o core. Providers, functions e ProviderConfigs sao entregues por GitOps a partir
# do ConfigMap platform-bootstrap.
resource "helm_release" "this" {
  name             = "crossplane"
  repository       = "https://charts.crossplane.io/stable"
  chart            = "crossplane"
  version          = var.chart_version
  namespace        = var.namespace
  create_namespace = true
  wait             = true
  timeout          = 600

  values = compact([
    yamlencode({
      serviceAccount = {
        create            = true
        customAnnotations = {}
      }
    }),
    var.extra_values,
  ])
}
