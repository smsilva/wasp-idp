mock_provider "helm" {}

run "chart_e_versao_fixados" {
  command = plan

  assert {
    condition     = helm_release.this.version == "10.4.0"
    error_message = "versao do chart argo-cd: esperado 10.4.0, recebido ${helm_release.this.version}"
  }

  assert {
    condition     = helm_release.this.repository == "https://argoproj.github.io/argo-helm"
    error_message = "repositorio: recebido ${helm_release.this.repository}"
  }
}

run "servico_e_cluster_ip_por_padrao" {
  command = plan

  assert {
    condition     = strcontains(helm_release.this.values[0], "ClusterIP")
    error_message = "sem ingress nesta camada, o server deve ser ClusterIP: ${helm_release.this.values[0]}"
  }
}

run "oidc_desligado_nao_emite_configuracao" {
  command = plan

  assert {
    condition     = !strcontains(helm_release.this.values[0], "oidc.config")
    error_message = "com oidc_enabled=false nao deveria haver bloco oidc.config"
  }
}

run "oidc_ligado_referencia_o_secret_por_placeholder" {
  command = plan

  variables {
    oidc_enabled   = true
    oidc_name      = "google"
    oidc_issuer    = "https://accounts.google.com"
    oidc_client_id = "exemplo.apps.googleusercontent.com"
  }

  assert {
    condition     = strcontains(helm_release.this.values[0], "$oidc.google.clientSecret")
    error_message = "o client secret deve ser referenciado por placeholder do argocd-secret, nunca em claro"
  }

  assert {
    condition     = !strcontains(helm_release.this.values[0], "clientSecret: \"")
    error_message = "nenhum client secret literal pode aparecer no values — iria para o state em claro"
  }
}
