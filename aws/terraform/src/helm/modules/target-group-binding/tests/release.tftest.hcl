mock_provider "helm" {}

variables {
  target_group_arn = "arn:aws:elasticloadbalancing:us-east-1:111122223333:targetgroup/poc-ek/abc123"
  vpc_id           = "vpc-0123456789abcdef0"
  service_name     = "istio-ingress"
  namespace        = "istio-ingress"
}

run "o_chart_e_local_nao_vem_de_repositorio" {
  command = plan

  # Não existe chart upstream para um CR só. O caminho alternativo seria
  # `kubernetes_manifest`, que faz dry-run server-side no PLAN e exige o CRD já registrado —
  # o que quebraria o apply único desta camada, já que o CRD chega junto, no mesmo apply.
  assert {
    condition     = helm_release.this.repository == null
    error_message = "o chart é local; declarar repositório aqui buscaria um chart que não existe"
  }

  assert {
    condition     = endswith(helm_release.this.chart, "/chart")
    error_message = "chart deve apontar para o diretório local, recebido ${helm_release.this.chart}"
  }
}

run "o_cr_aponta_para_a_target_group_do_terraform" {
  command = plan

  # O ARN muda a cada recriação da target group (`name_prefix` + create_before_destroy), então
  # ele TEM de chegar por referência de Terraform. Um values file colado à mão fica velho no
  # primeiro replace, e o sintoma é target group vazia com tudo aparentemente saudável.
  assert {
    condition     = yamldecode(helm_release.this.values[0]).targetGroupARN == "arn:aws:elasticloadbalancing:us-east-1:111122223333:targetgroup/poc-ek/abc123"
    error_message = "targetGroupARN deve chegar pela variável, nunca fixo no código"
  }

  assert {
    condition     = yamldecode(helm_release.this.values[0]).vpcID == "vpc-0123456789abcdef0"
    error_message = "vpcID deve chegar pela variável"
  }
}

run "e_acompanha_outra_celula" {
  command = plan

  variables {
    target_group_arn = "arn:aws:elasticloadbalancing:us-west-2:444455556666:targetgroup/outra/xyz789"
    vpc_id           = "vpc-0fedcba9876543210"
  }

  # Segunda execução com valores diferentes: uma sozinha passaria mesmo com o ARN fixo no
  # código, desde que igual ao do fixture.
  assert {
    condition = alltrue([
      yamldecode(helm_release.this.values[0]).targetGroupARN == "arn:aws:elasticloadbalancing:us-west-2:444455556666:targetgroup/outra/xyz789",
      yamldecode(helm_release.this.values[0]).vpcID == "vpc-0fedcba9876543210",
    ])
    error_message = "o módulo tem de servir qualquer célula sem alteração"
  }
}

run "o_alvo_e_o_service_do_gateway_na_porta_do_pod" {
  command = plan

  assert {
    condition     = yamldecode(helm_release.this.values[0]).serviceRef.name == "istio-ingress"
    error_message = "serviceRef.name deve casar com o Service do gateway"
  }

  # 80, não 8080: o chart do gateway mapeia o Service 80 → targetPort 80, e é a 80 que a
  # target group declara e que o security group do cluster libera. 8080 é do Istio antigo, e o
  # sintoma de errar aqui é "nenhum target saudável" sem nada errado no cluster.
  assert {
    condition     = yamldecode(helm_release.this.values[0]).serviceRef.port == 80
    error_message = "serviceRef.port: esperado 80, recebido ${yamldecode(helm_release.this.values[0]).serviceRef.port}"
  }

  # `ip`, não `instance`: a target group de `src/ingress` é target_type = ip, e o registro é
  # dos IPs dos pods do gateway — não dos nós.
  assert {
    condition     = yamldecode(helm_release.this.values[0]).targetType == "ip"
    error_message = "targetType deve casar com o da target group (ip)"
  }
}

run "o_cr_vive_no_namespace_do_gateway" {
  command = plan

  # `serviceRef` não atravessa namespace: o CR tem de nascer onde o Service está, senão o
  # controller reporta que não achou o Service e a target group fica vazia.
  assert {
    condition     = helm_release.this.namespace == "istio-ingress"
    error_message = "o CR tem de viver no mesmo namespace do Service que referencia"
  }

  # O namespace é do módulo do Istio; criá-lo aqui de novo daria duas fontes para o mesmo
  # objeto — e a que vencesse a corrida poderia criá-lo sem o rótulo de injeção.
  assert {
    condition     = helm_release.this.create_namespace == false
    error_message = "o namespace é criado pelo módulo ingress-istio, não por este"
  }
}

run "o_nome_do_release_nao_colide_com_o_do_gateway" {
  command = plan

  # Neste desenho `gateway_service_name == gateway_release_name` (o chart do gateway nomeia o
  # Service pelo release). Logo, serviceRef.name aponta para um Service que TEM o mesmo nome do
  # release `istio-ingress` do gateway — e o Helm identifica release por (namespace, name). Se
  # este release herdasse esse nome no mesmo namespace, o apply real falharia com "cannot
  # re-use a name that is still in use", erro que o mock_provider "helm" NÃO reproduz (não
  # simula a key de releases do cluster). A asserção de aqui é o único guard offline.
  assert {
    condition     = helm_release.this.name != yamldecode(helm_release.this.values[0]).serviceRef.name
    error_message = "o nome do release nao pode igualar serviceRef.name: é o nome do release do gateway, e haveria colisao de release no mesmo namespace"
  }

  assert {
    condition     = helm_release.this.name != "istio-ingress"
    error_message = "o nome do release nao pode ser istio-ingress: colide com o release do gateway no mesmo namespace"
  }
}

run "o_controller_nao_gerencia_security_group" {
  command = plan

  # As regras de SG do gateway são do Terraform (as duas aws_vpc_security_group_ingress_rule
  # da camada control-plane), e a policy mínima da Pod Identity não concede actions de SG.
  # Passar `networking` faria o controller tentar mexer nelas e falhar em AccessDenied.
  assert {
    condition     = !contains(keys(yamldecode(helm_release.this.values[0])), "networking")
    error_message = "o values não deve carregar bloco networking — as regras de SG são do Terraform"
  }
}
