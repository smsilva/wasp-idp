mock_provider "aws" {}

variables {
  name       = "test-control-plane"
  subnet_ids = ["subnet-aaa", "subnet-bbb", "subnet-ccc", "subnet-ddd"]
}

run "modo_de_autenticacao_e_api_puro" {
  command = plan

  assert {
    condition     = aws_eks_cluster.this.access_config[0].authentication_mode == "API"
    error_message = "authentication_mode deveria ser API (sem aws-auth ConfigMap), recebido ${aws_eks_cluster.this.access_config[0].authentication_mode}"
  }
}

run "cluster_usa_todas_as_subnets_recebidas" {
  command = plan

  assert {
    condition     = length(aws_eks_cluster.this.vpc_config[0].subnet_ids) == 4
    error_message = "o control plane deve ficar nas 4 subnets (imutavel apos a criacao), recebidas ${length(aws_eks_cluster.this.vpc_config[0].subnet_ids)}"
  }
}

run "versao_default_do_kubernetes" {
  command = plan

  assert {
    condition     = aws_eks_cluster.this.version == "1.34"
    error_message = "versao default do kubernetes: esperado 1.34, recebido ${aws_eks_cluster.this.version}"
  }
}

run "menos_de_duas_subnets_e_erro" {
  command = plan

  variables {
    subnet_ids = ["subnet-aaa"]
  }

  expect_failures = [var.subnet_ids]
}

run "addons_de_base_sao_dois_com_overwrite" {
  command = plan

  assert {
    condition     = length(aws_eks_addon.this) == 2
    error_message = "esperados 2 addons de base, recebidos ${length(aws_eks_addon.this)}"
  }

  assert {
    condition     = aws_eks_addon.this["eks-pod-identity-agent"].resolve_conflicts_on_create == "OVERWRITE"
    error_message = "addon deveria resolver conflitos com OVERWRITE, recebido ${aws_eks_addon.this["eks-pod-identity-agent"].resolve_conflicts_on_create}"
  }
}

run "role_dos_nos_tem_as_tres_policies_gerenciadas" {
  command = plan

  assert {
    condition     = length(aws_iam_role_policy_attachment.node) == 3
    error_message = "o role dos nos precisa de WorkerNode + ECR ReadOnly + CNI, recebidos ${length(aws_iam_role_policy_attachment.node)}"
  }
}
