mock_provider "helm" {}
mock_provider "kubernetes" {}

variables {
  host        = "services.poc-eks.nonprod.example.com"
  gateway_ref = "istio-ingress/inbound"
}

run "o_chart_e_local" {
  command = plan

  assert {
    condition     = helm_release.this.repository == null
    error_message = "o chart é local — o VirtualService é um CR, e o CRD chega no mesmo apply"
  }
}

run "a_rota_aponta_para_o_gateway_da_celula" {
  command = plan

  # Forma `<namespace>/<nome>`: o VirtualService vive no namespace do workload e o Gateway no
  # do ingress. O nome curto resolveria aqui, onde o Gateway não está, e a rota não existiria —
  # sem erro nenhum.
  assert {
    condition     = yamldecode(helm_release.this.values[0]).gateway == "istio-ingress/inbound"
    error_message = "gateway deve chegar qualificado por namespace"
  }

  assert {
    condition     = yamldecode(helm_release.this.values[0]).host == "services.poc-eks.nonprod.example.com"
    error_message = "host deve chegar pela variável"
  }
}

run "e_acompanha_outra_celula" {
  command = plan

  variables {
    host        = "services.outra.prod.example.net"
    gateway_ref = "borda/entrada"
  }

  # Segunda execução com valores diferentes: uma sozinha passaria mesmo com o host fixo no
  # código, desde que igual ao do fixture.
  assert {
    condition = alltrue([
      yamldecode(helm_release.this.values[0]).host == "services.outra.prod.example.net",
      yamldecode(helm_release.this.values[0]).gateway == "borda/entrada",
    ])
    error_message = "o módulo tem de servir qualquer célula sem alteração"
  }

  assert {
    condition     = output.url == "https://services.outra.prod.example.net/"
    error_message = "a URL de prova tem de acompanhar o host, recebida ${output.url}"
  }
}

run "gateway_ref_sem_namespace_e_recusado" {
  command = plan

  variables {
    gateway_ref = "inbound"
  }

  expect_failures = [var.gateway_ref]
}

run "o_workload_entra_na_malha" {
  command = plan

  assert {
    condition     = kubernetes_namespace_v1.this.metadata[0].name == "httpbin"
    error_message = "namespace: esperado httpbin"
  }

  assert {
    condition     = kubernetes_namespace_v1.this.metadata[0].labels["istio-injection"] == "enabled"
    error_message = "o namespace do workload entra na malha"
  }

  # Quem cria o namespace é o recurso kubernetes, que carrega o rótulo. Deixar o helm criar
  # também faria o namespace nascer sem rótulo se ele ganhasse a corrida.
  assert {
    condition     = helm_release.this.create_namespace == false
    error_message = "o namespace é criado pelo recurso kubernetes, não pelo helm"
  }
}

run "a_imagem_e_fixada" {
  command = plan

  assert {
    condition     = yamldecode(helm_release.this.values[0]).image.tag == "2.21.0"
    error_message = "a tag da imagem deve ser fixada, recebida ${yamldecode(helm_release.this.values[0]).image.tag}"
  }
}
