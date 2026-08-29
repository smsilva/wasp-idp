mock_provider "helm" {}
mock_provider "kubernetes" {}

run "as_tres_releases_usam_o_mesmo_repositorio_e_a_mesma_versao" {
  command = plan

  # base, istiod e gateway são o mesmo Istio partido em três charts. Versões diferentes entre
  # eles é combinação não suportada pelo projeto, e o sintoma aparece longe daqui — o gateway
  # nasce com um proxy de versão que o istiod não sabe configurar.
  assert {
    condition = alltrue([
      helm_release.base.repository == "https://istio-release.storage.googleapis.com/charts",
      helm_release.istiod.repository == "https://istio-release.storage.googleapis.com/charts",
      helm_release.gateway.repository == "https://istio-release.storage.googleapis.com/charts",
    ])
    error_message = "os três releases têm de vir do repositório oficial do istio-release"
  }

  assert {
    condition = alltrue([
      helm_release.base.version == "1.30.4",
      helm_release.istiod.version == "1.30.4",
      helm_release.gateway.version == "1.30.4",
    ])
    error_message = "os três releases têm de compartilhar a MESMA versão de chart"
  }

  assert {
    condition = alltrue([
      helm_release.base.chart == "base",
      helm_release.istiod.chart == "istiod",
      helm_release.gateway.chart == "gateway",
    ])
    error_message = "charts: esperados base, istiod e gateway"
  }
}

run "uma_versao_so_move_os_tres" {
  command = plan

  variables {
    chart_version = "1.29.2"
  }

  # Duas execuções com valores diferentes: uma sozinha passaria mesmo com a versão fixa no
  # código, desde que igual à do fixture.
  assert {
    condition = alltrue([
      helm_release.base.version == "1.29.2",
      helm_release.istiod.version == "1.29.2",
      helm_release.gateway.version == "1.29.2",
    ])
    error_message = "chart_version tem de mover os três releases juntos"
  }
}

run "o_plano_de_controle_vive_no_istio_system" {
  command = plan

  assert {
    condition     = helm_release.base.namespace == "istio-system" && helm_release.istiod.namespace == "istio-system"
    error_message = "base e istiod vivem em istio-system"
  }

  # Só o `base` cria o namespace; pedir criação nos dois deixa duas fontes para o mesmo objeto.
  assert {
    condition     = helm_release.base.create_namespace && helm_release.istiod.create_namespace == false
    error_message = "quem cria istio-system é o release `base`, uma vez só"
  }
}

run "os_tres_esperam_ficar_prontos" {
  command = plan

  # `base` registra os CRDs que o istiod consome; o istiod publica o webhook de injeção sem o
  # qual o pod do gateway nasce com `image: auto` e nunca resolve. Sem `wait`, os dois casos
  # falham no release seguinte, longe da causa.
  assert {
    condition = alltrue([
      helm_release.base.wait,
      helm_release.istiod.wait,
      helm_release.gateway.wait,
    ])
    error_message = "os três releases precisam de wait — cada um habilita o próximo"
  }
}

run "o_gateway_nao_pede_load_balancer" {
  command = plan

  # ADR 0008: quem materializa o load balancer é o Terraform (`src/ingress`), e a ligação
  # pods → target group é o TargetGroupBinding. Um Service type=LoadBalancer aqui pediria um
  # segundo NLB — que o LBC desta célula nem tem permissão para criar, então o sintoma seria
  # um Service eternamente em `<pending>`.
  assert {
    condition     = yamldecode(helm_release.gateway.values[0]).service.type == "ClusterIP"
    error_message = "o Service do gateway tem de ser ClusterIP, nunca LoadBalancer"
  }
}

run "o_gateway_nasce_no_proprio_namespace_com_injecao_ligada" {
  command = plan

  assert {
    condition     = kubernetes_namespace_v1.gateway.metadata[0].name == "istio-ingress"
    error_message = "namespace do gateway: esperado istio-ingress"
  }

  # O chart do gateway entrega um Deployment com `image: auto` — quem materializa o proxy é o
  # webhook de injeção do istiod. Sem o rótulo, o pod fica com `auto` como nome de imagem e o
  # ImagePullBackOff não diz que a causa é um label faltando no namespace.
  assert {
    condition     = kubernetes_namespace_v1.gateway.metadata[0].labels["istio-injection"] == "enabled"
    error_message = "o namespace do gateway precisa de istio-injection=enabled"
  }

  assert {
    condition     = helm_release.gateway.namespace == "istio-ingress"
    error_message = "o release do gateway tem de aterrissar no namespace criado aqui"
  }

  # Quem cria o namespace é o `kubernetes_namespace_v1` (é ele que carrega o rótulo). Deixar o
  # helm criar também faria o namespace nascer sem rótulo se ele ganhasse a corrida.
  assert {
    condition     = helm_release.gateway.create_namespace == false
    error_message = "o namespace do gateway é criado pelo recurso kubernetes, não pelo helm"
  }
}

run "o_seletor_do_gateway_perde_o_prefixo_istio" {
  command = plan

  # O chart tira o prefixo `istio-` do nome do release ao montar o rótulo `istio:` — release
  # `istio-ingress` produz `istio: ingress`. É esse valor que o `Gateway` CR seleciona; errar
  # aqui dá 503 sem nada aparentemente errado no cluster.
  assert {
    condition     = output.gateway_selector == "ingress"
    error_message = "release istio-ingress deve produzir o seletor `ingress`, recebido ${output.gateway_selector}"
  }
}

run "e_um_nome_sem_o_prefixo_fica_intacto" {
  command = plan

  variables {
    gateway_release_name = "borda"
  }

  assert {
    condition     = output.gateway_selector == "borda"
    error_message = "nome sem prefixo `istio-` deve passar intacto, recebido ${output.gateway_selector}"
  }
}

run "o_contrato_com_o_target_group_binding" {
  command = plan

  # É por estes dois que o TargetGroupBinding aponta o Service do gateway. Derivá-los aqui
  # evita que o passo seguinte cole o nome à mão e descubra a divergência só no reconcile.
  assert {
    condition     = output.gateway_service_name == "istio-ingress"
    error_message = "o Service do gateway tem o nome do release"
  }

  assert {
    condition     = output.gateway_namespace == "istio-ingress"
    error_message = "namespace do gateway no output: esperado istio-ingress"
  }
}

run "extra_values_por_release" {
  command = plan

  variables {
    istiod_extra_values  = "meshConfig:\n  accessLogFile: /dev/stdout"
    gateway_extra_values = "replicaCount: 3"
  }

  # O gateway tem values base (o ClusterIP), então o extra entra como SEGUNDO documento — a
  # ordem é o que faz ele sobrescrever. O istiod não tem base nenhum, então o extra é o único.
  assert {
    condition     = length(helm_release.gateway.values) == 2
    error_message = "gateway_extra_values deve entrar depois do values base, para sobrescrevê-lo"
  }

  assert {
    condition     = yamldecode(helm_release.gateway.values[1]).replicaCount == 3
    error_message = "gateway_extra_values deve chegar ao release sem alteração"
  }

  assert {
    condition     = length(helm_release.istiod.values) == 1
    error_message = "istiod_extra_values deve ser o único documento do release do istiod"
  }

  assert {
    condition     = yamldecode(helm_release.istiod.values[0]).meshConfig.accessLogFile == "/dev/stdout"
    error_message = "istiod_extra_values deve chegar ao release sem alteração"
  }
}

run "sem_extra_values_nao_ha_documento_vazio" {
  command = plan

  # `compact` existe para isto: string vazia viraria um documento YAML vazio no release, que o
  # helm aceita calado e que aparece como diff sem causa no próximo plan.
  assert {
    condition     = length(helm_release.istiod.values) == 0
    error_message = "sem extra_values o istiod não deve ter documento nenhum"
  }

  assert {
    condition     = length(helm_release.gateway.values) == 1
    error_message = "sem extra_values o gateway deve ter só o values base"
  }
}
