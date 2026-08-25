resource "helm_release" "this" {
  name             = "external-secrets"
  repository       = "https://charts.external-secrets.io"
  chart            = "external-secrets"
  version          = var.chart_version
  namespace        = var.namespace
  create_namespace = true
  wait             = true
  timeout          = 600

  values = compact([
    yamlencode({
      installCRDs = true
      serviceAccount = {
        create = true
        name   = var.service_account_name
      }
    }),
    var.extra_values,
  ])
}
