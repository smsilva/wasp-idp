mock_provider "aws" {}

variables {
  cluster_name  = "test-control-plane"
  node_role_arn = "arn:aws:iam::123456789012:role/test-node"
  subnet_ids    = ["subnet-priv-a", "subnet-priv-b"]
}

run "grupo_default_existe_com_valores_de_referencia" {
  command = plan

  assert {
    condition     = aws_eks_node_group.this["default"].instance_types == tolist(["t3.medium"])
    error_message = "instance type default: esperado t3.medium, recebido ${join(",", aws_eks_node_group.this["default"].instance_types)}"
  }

  assert {
    condition     = aws_eks_node_group.this["default"].capacity_type == "ON_DEMAND"
    error_message = "capacity type default: esperado ON_DEMAND, recebido ${aws_eks_node_group.this["default"].capacity_type}"
  }

  assert {
    condition     = aws_eks_node_group.this["default"].scaling_config[0].desired_size == 2
    error_message = "desired size default: esperado 2, recebido ${aws_eks_node_group.this["default"].scaling_config[0].desired_size}"
  }
}

run "nos_ficam_apenas_em_subnets_privadas" {
  command = plan

  assert {
    condition     = length(aws_eks_node_group.this["default"].subnet_ids) == 2
    error_message = "os nos devem usar so as 2 subnets privadas, recebidas ${length(aws_eks_node_group.this["default"].subnet_ids)}"
  }
}

run "capacity_type_invalido_e_erro" {
  command = plan

  variables {
    node_groups = {
      default = { capacity_type = "RESERVED" }
    }
  }

  expect_failures = [var.node_groups]
}

run "mais_de_um_grupo_gera_mais_de_um_recurso" {
  command = plan

  variables {
    node_groups = {
      default = {}
      spot    = { capacity_type = "SPOT" }
    }
  }

  assert {
    condition     = length(aws_eks_node_group.this) == 2
    error_message = "esperados 2 node groups, recebidos ${length(aws_eks_node_group.this)}"
  }
}
