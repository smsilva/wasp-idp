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

run "tres_pod_identities_uma_por_consumidor" {
  command = plan

  # role_arn so existe depois do apply; role_name deriva de var.name e ja e conhecido no
  # plan. Verificar o nome prova que os tres modulos foram instanciados e nomeados certo,
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
}

run "configmap_de_bootstrap_tem_as_sete_chaves" {
  command = plan

  assert {
    condition     = length(keys(kubernetes_config_map_v1.platform_bootstrap.data)) == 7
    error_message = "o platform-bootstrap e o contrato com o GitOps: esperadas 7 chaves, recebidas ${length(keys(kubernetes_config_map_v1.platform_bootstrap.data))}"
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
