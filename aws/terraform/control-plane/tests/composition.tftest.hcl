mock_provider "aws" {}

mock_provider "aws" {
  alias = "network"
}

mock_provider "kubernetes" {}
mock_provider "helm" {}

variables {
  name               = "control-plane"
  region             = "us-east-1"
  aws_profile        = "cicd"
  network_profile    = "network"
  hub_vpc_name       = "poc-hub-vpc"
  vpc_cidr           = "10.2.0.0/16"
  availability_zones = ["us-east-1a", "us-east-1b"]
  target_account_ids = ["000000000000"]
  network_account_id = "111111111111"
  # RFC 5737, bloco de documentacao. Na vida real vem do generate-tfvars, que descobre o IP
  # publico da maquina que vai rodar o apply.
  public_access_cidrs = ["203.0.113.10/32"]
}

# Obrigatório desde o 2.4: o cidr_block desta VPC alimenta a regra de 443 do security group
# do cluster, e a validação de schema do provider (que roda sob mock, client-side) recusa o
# valor sintético — o plan inteiro morre com "must be a valid IPv4 CIDR".
override_data {
  target = data.aws_vpc.hub
  values = {
    id         = "vpc-hub000000000001"
    cidr_block = "10.1.0.0/16"
  }
}

run "spoke_usa_o_segundo_octeto_reservado" {
  command = plan

  assert {
    condition     = module.network.vpc_cidr == "10.2.0.0/16"
    error_message = "a spoke da conta cicd e o N=2 do supernet, recebido ${module.network.vpc_cidr}"
  }
}

run "nat_gateway_ligado_na_spoke" {
  command = plan

  assert {
    condition     = var.enable_nat_gateway
    error_message = "sem TGW nao ha rota pelo hub; os nos precisam de NAT para alcancar a API da AWS e os registries"
  }
}

run "quatro_pod_identities_uma_por_consumidor" {
  command = plan

  # role_arn so existe depois do apply; role_name deriva de var.name e ja e conhecido no
  # plan. Verificar o nome prova que os modulos foram instanciados e nomeados certo,
  # sem exigir um apply contra a AWS.
  assert {
    condition     = module.pod_identity_ebs_csi.role_name == "control-plane-ebs-csi"
    error_message = "Pod Identity do EBS CSI: recebido ${module.pod_identity_ebs_csi.role_name}"
  }

  assert {
    condition     = module.pod_identity_eso.role_name == "control-plane-external-secrets"
    error_message = "Pod Identity do External Secrets: recebido ${module.pod_identity_eso.role_name}"
  }

  assert {
    condition     = module.pod_identity_crossplane.role_name == "control-plane-crossplane"
    error_message = "Pod Identity do Crossplane: recebido ${module.pod_identity_crossplane.role_name}"
  }

  # 3.1: o CHART do LBC vem por GitOps, mas o role e desta camada. Sem ele o
  # TargetGroupBinding sobe e nunca registra target, com AccessDenied so no log do controller.
  assert {
    condition     = module.pod_identity_lbc.role_name == "control-plane-load-balancer-controller"
    error_message = "Pod Identity do LBC: recebido ${module.pod_identity_lbc.role_name}"
  }
}

run "configmap_de_bootstrap_carrega_o_contrato_inteiro" {
  command = plan

  # A contagem sozinha nao diria QUAL chave falta; as duas assercoes juntas pegam tanto a
  # chave removida por engano quanto a acrescentada sem passar por aqui.
  assert {
    condition = toset(keys(kubernetes_config_map_v1.platform_bootstrap.data)) == toset([
      "region",
      "clusterName",
      "hubVpcId",
      "spokeSubnetIds",
      "crossplaneRoleArn",
      "networkAccountId",
      "targetAccountIds",
      "ingressTargetGroupArn",
      "loadBalancerControllerRoleArn",
    ])
    error_message = "o platform-bootstrap e o contrato com o GitOps; chaves recebidas: ${jsonencode(sort(keys(kubernetes_config_map_v1.platform_bootstrap.data)))}"
  }

  assert {
    condition     = kubernetes_config_map_v1.platform_bootstrap.metadata[0].namespace == "crossplane-system"
    error_message = "o ConfigMap vive em crossplane-system, recebido ${kubernetes_config_map_v1.platform_bootstrap.metadata[0].namespace}"
  }
}

run "cidr_fora_do_supernet_e_erro" {
  command = plan

  variables {
    vpc_cidr = "192.168.0.0/16"
  }

  expect_failures = [var.vpc_cidr]
}

# A restricao do endpoint atravessa duas camadas: o root escolhe o valor, o modulo o entrega
# ao vpc_config. Um desses fios cortado deixa a API aberta sem nada reclamar.
#
# Cenario de endpoint ABERTO, que desde o 2.5 e break-glass e nao o default — com ele fechado
# o atributo e omitido e este output fica "known after apply".
run "o_cidr_do_root_chega_ao_endpoint_do_cluster" {
  command = plan

  variables {
    endpoint_public_access = true
  }

  assert {
    condition     = module.cluster.public_access_cidrs == toset(["203.0.113.10/32"])
    error_message = "o public_access_cidrs do root deveria chegar ao endpoint do cluster, recebido ${jsonencode(module.cluster.public_access_cidrs)}"
  }
}

# Politica da celula, nao semantica da AWS: 0.0.0.0/0 e um valor legitimo para o recurso e
# recusado aqui de proposito. Abrir exige editar a validacao, que aparece em diff.
run "o_mundo_e_recusado_mesmo_explicito" {
  command = plan

  variables {
    public_access_cidrs = ["0.0.0.0/0"]
  }

  expect_failures = [var.public_access_cidrs]
}
