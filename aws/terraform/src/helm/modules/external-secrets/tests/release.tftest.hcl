mock_provider "helm" {}

run "chart_e_versao_fixados" {
  command = plan

  assert {
    condition     = helm_release.this.chart == "external-secrets"
    error_message = "chart: esperado external-secrets, recebido ${helm_release.this.chart}"
  }

  assert {
    condition     = helm_release.this.version == "2.9.0"
    error_message = "versao do chart deve ser fixada em 2.9.0, recebida ${helm_release.this.version}"
  }

  assert {
    condition     = helm_release.this.repository == "https://charts.external-secrets.io"
    error_message = "repositorio: recebido ${helm_release.this.repository}"
  }
}

run "release_espera_ficar_pronto" {
  command = plan

  assert {
    condition     = helm_release.this.wait
    error_message = "wait deve ser true — o ArgoCD e o Crossplane vem depois e dependem do CRD estar registrado"
  }

  assert {
    condition     = helm_release.this.timeout == 600
    error_message = "timeout: esperado 600, recebido ${helm_release.this.timeout}"
  }
}

run "namespace_default" {
  command = plan

  assert {
    condition     = helm_release.this.namespace == "external-secrets"
    error_message = "namespace: esperado external-secrets, recebido ${helm_release.this.namespace}"
  }
}
