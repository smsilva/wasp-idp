mock_provider "helm" {}

variables {
  cluster_name = "poc-eks"
  region       = "us-east-1"
  vpc_id       = "vpc-0123456789abcdef0"
}

run "chart_e_versao_fixados" {
  command = plan

  assert {
    condition     = helm_release.this.chart == "aws-load-balancer-controller"
    error_message = "chart: esperado aws-load-balancer-controller, recebido ${helm_release.this.chart}"
  }

  assert {
    condition     = helm_release.this.version == "3.5.0"
    error_message = "versão do chart deve ser fixada em 3.5.0, recebida ${helm_release.this.version}"
  }

  assert {
    condition     = helm_release.this.repository == "https://aws.github.io/eks-charts"
    error_message = "repositório: recebido ${helm_release.this.repository}"
  }
}

run "release_espera_ficar_pronto" {
  command = plan

  # O TargetGroupBinding é um CRD registrado por ESTE chart. Sem `wait`, o recurso que o
  # consome corre contra o registro do CRD e falha com "no matches for kind".
  assert {
    condition     = helm_release.this.wait
    error_message = "wait deve ser true — o TargetGroupBinding depende do CRD deste chart já estar registrado"
  }

  assert {
    condition     = helm_release.this.timeout == 600
    error_message = "timeout: esperado 600, recebido ${helm_release.this.timeout}"
  }
}

run "namespace_default_e_kube_system_sem_criar" {
  command = plan

  assert {
    condition     = helm_release.this.namespace == "kube-system"
    error_message = "namespace: esperado kube-system, recebido ${helm_release.this.namespace}"
  }

  # kube-system sempre existe; pedir criação só acrescentaria uma chamada que pode falhar.
  assert {
    condition     = helm_release.this.create_namespace == false
    error_message = "create_namespace deve ser false — kube-system já existe no cluster"
  }
}

run "identidade_do_pod_casa_com_a_pod_identity" {
  command = plan

  # O par (namespace, serviceAccount) é o mesmo que a PodIdentityAssociation aponta. Divergir
  # aqui não falha o apply: falha em AccessDenied no log do controller, longe da causa.
  assert {
    condition     = yamldecode(helm_release.this.values[0]).serviceAccount.name == "aws-load-balancer-controller"
    error_message = "serviceAccount.name deve casar com a Pod Identity association"
  }

  assert {
    condition     = yamldecode(helm_release.this.values[0]).serviceAccount.create
    error_message = "serviceAccount.create deve ser true — quem cria a SA é o chart, não o Terraform"
  }
}

run "sem_imds_no_caminho" {
  command = plan

  # clusterName/region/vpcId explícitos: sem eles o controller resolve por IMDS, que depende
  # do hop limit do nó. O dado é conhecido no apply — não há razão para descobrir em runtime.
  assert {
    condition     = yamldecode(helm_release.this.values[0]).clusterName == "poc-eks"
    error_message = "clusterName deve ser explícito, nunca resolvido por IMDS"
  }

  assert {
    condition     = yamldecode(helm_release.this.values[0]).region == "us-east-1"
    error_message = "region deve ser explícita, nunca resolvida por IMDS"
  }

  assert {
    condition     = yamldecode(helm_release.this.values[0]).vpcId == "vpc-0123456789abcdef0"
    error_message = "vpcId deve ser explícito, nunca resolvido por IMDS"
  }
}

run "controller_nao_pode_criar_load_balancer_proprio" {
  command = plan

  # ADR 0004: ingress único, pelo hub. O NLB é do Terraform. Um LBC capaz de materializar
  # load balancer a partir de Ingress ou de Service type=LoadBalancer reabriria a porta que
  # essa decisão fechou — e a policy da Pod Identity (control-plane/main.tf) nem concede as
  # actions para isso, então o sintoma seria AccessDenied em vez de uma recusa clara.
  assert {
    condition     = yamldecode(helm_release.this.values[0]).enableServiceMutatorWebhook == false
    error_message = "enableServiceMutatorWebhook deve ser false — senão este controller vira o default de todo Service type=LoadBalancer do cluster"
  }

  assert {
    condition     = yamldecode(helm_release.this.values[0]).createIngressClassResource == false
    error_message = "createIngressClassResource deve ser false — não há Ingress ALB nesta célula"
  }

  assert {
    condition     = yamldecode(helm_release.this.values[0]).ingressClassParams.create == false
    error_message = "ingressClassParams.create deve ser false — sem IngressClass, o CRD de params não tem uso"
  }
}

run "integracoes_fora_do_escopo_desligadas" {
  command = plan

  # Shield/WAF são consultados pelo controller ao reconciliar; a policy mínima não concede
  # essas actions. Deixar no default (nulo) faria o controller descobrir por tentativa.
  assert {
    condition = alltrue([
      yamldecode(helm_release.this.values[0]).enableShield == false,
      yamldecode(helm_release.this.values[0]).enableWaf == false,
      yamldecode(helm_release.this.values[0]).enableWafv2 == false,
    ])
    error_message = "Shield/WAF/WAFv2 devem ser explicitamente false — a policy mínima não concede essas actions"
  }
}

run "extra_values_e_mesclado_depois_do_base" {
  command = plan

  variables {
    extra_values = "replicaCount: 1"
  }

  assert {
    condition     = length(helm_release.this.values) == 2
    error_message = "extra_values deve entrar como segundo documento, para sobrescrever o base"
  }

  assert {
    condition     = yamldecode(helm_release.this.values[1]).replicaCount == 1
    error_message = "extra_values deve chegar ao release sem alteração"
  }
}

run "sem_extra_values_o_release_tem_um_documento_so" {
  command = plan

  assert {
    condition     = length(helm_release.this.values) == 1
    error_message = "extra_values vazio não deve virar documento YAML vazio no release"
  }
}
