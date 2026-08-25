mock_provider "helm" {}

run "chart_e_versao_fixados" {
  command = plan

  assert {
    condition     = helm_release.this.version == "2.4.0"
    error_message = "versao do chart crossplane: esperado 2.4.0, recebido ${helm_release.this.version}"
  }

  assert {
    condition     = helm_release.this.repository == "https://charts.crossplane.io/stable"
    error_message = "repositorio: recebido ${helm_release.this.repository}"
  }

  assert {
    condition     = helm_release.this.namespace == "crossplane-system"
    error_message = "namespace: esperado crossplane-system, recebido ${helm_release.this.namespace}"
  }
}

run "nenhum_provider_e_instalado_pelo_terraform" {
  command = plan

  assert {
    condition     = !strcontains(helm_release.this.values[0], "provider-aws")
    error_message = "providers do Crossplane chegam por GitOps, nao pelo Terraform: ${helm_release.this.values[0]}"
  }
}
