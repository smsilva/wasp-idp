locals {
  # O clientSecret NAO aparece aqui. O placeholder $oidc.<nome>.clientSecret e resolvido
  # pelo ArgoCD contra o secret argocd-secret, onde o ESO o mescla com creationPolicy Merge.
  oidc_config = var.oidc_enabled ? {
    "oidc.config" = yamlencode({
      name            = var.oidc_name
      issuer          = var.oidc_issuer
      clientID        = var.oidc_client_id
      clientSecret    = "$oidc.${var.oidc_name}.clientSecret"
      requestedScopes = ["openid", "profile", "email"]
    })
  } : {}
}

resource "helm_release" "this" {
  name             = "argo-cd"
  repository       = "https://argoproj.github.io/argo-helm"
  chart            = "argo-cd"
  version          = var.chart_version
  namespace        = var.namespace
  create_namespace = true
  wait             = true
  timeout          = 600

  values = compact([
    yamlencode({
      configs = {
        cm = merge({
          url = var.server_url
        }, local.oidc_config)
        params = {
          "server.insecure" = true
        }
      }
      server = {
        service = {
          type = "ClusterIP"
        }
      }
    }),
    var.extra_values,
  ])
}
