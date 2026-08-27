mock_provider "aws" {}

variables {
  name       = "test-control-plane"
  subnet_ids = ["subnet-aaa", "subnet-bbb", "subnet-ccc", "subnet-ddd"]
  # Sem isto o modulo recusa o plan de proposito: endpoint publico ligado com lista vazia
  # e como a AWS entende 0.0.0.0/0. O 203.0.113.0/24 e o bloco de documentacao da RFC 5737.
  public_access_cidrs = ["203.0.113.10/32"]
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
    condition     = aws_eks_cluster.this.version == "1.36"
    error_message = "versao default do kubernetes: esperado 1.36, recebido ${aws_eks_cluster.this.version}"
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

# O endpoint da API e a maior superficie exposta da celula. A lista chega ao vpc_config ou
# nao chega — e se nao chegar, a AWS abre para 0.0.0.0/0 sem reclamar de nada.
run "os_cidrs_autorizados_chegam_ao_endpoint_publico" {
  command = plan

  assert {
    condition     = aws_eks_cluster.this.vpc_config[0].public_access_cidrs == toset(["203.0.113.10/32"])
    error_message = "public_access_cidrs deveria chegar ao vpc_config, recebido ${jsonencode(aws_eks_cluster.this.vpc_config[0].public_access_cidrs)}"
  }

  assert {
    condition     = aws_eks_cluster.this.vpc_config[0].endpoint_private_access
    error_message = "o endpoint privado fica ligado: e o caminho que sobrevive ao fechamento do publico no 2.5"
  }
}

# Este e o Known Broken 3 virado teste: omitir a lista era o caminho silencioso para expor
# a API ao mundo. Agora e erro de validacao, antes de qualquer chamada a AWS.
run "endpoint_publico_sem_cidr_e_erro" {
  command = plan

  variables {
    public_access_cidrs = []
  }

  expect_failures = [var.public_access_cidrs]
}

# Com o endpoint publico desligado nao ha o que restringir, e exigir a lista ali seria
# atrapalhar o caminho de destino (2.5, endpoint so privado).
run "sem_endpoint_publico_a_lista_vazia_e_valida" {
  command = plan

  variables {
    endpoint_public_access = false
    public_access_cidrs    = []
  }

  assert {
    condition     = aws_eks_cluster.this.vpc_config[0].endpoint_public_access == false
    error_message = "o endpoint publico deveria estar desligado neste cenario"
  }
}

# 2.5 — com o endpoint publico desligado, o atributo tem de ser OMITIDO, nao mandado vazio.
# A doc do provider: public_access_cidrs indica quem alcanca o endpoint publico "when
# enabled", e o Terraform "will only perform drift detection of its value when present in a
# configuration". Presente e vazio, com o endpoint fechado, e o pior dos mundos: a EKS guarda
# 0.0.0.0/0 como default e todo plan proporia mudar para [] — perpetual diff que nunca
# converge, mesma familia do attachment cross-conta.
#
# A asserção lê o LOCAL pelo output, nao o vpc_config: com o atributo omitido o valor no
# recurso e "known after apply" (Optional+Computed), e asserção sobre unknown nao avalia.
run "endpoint_publico_desligado_omite_a_lista_em_vez_de_mandar_vazia" {
  command = plan

  variables {
    endpoint_public_access = false
    # Nao-vazia DE PROPOSITO: o valor tem de ser descartado pelo flag, nao por acaso de a
    # lista estar vazia. Sem isto a asserção passaria com a condicional invertida.
    public_access_cidrs = ["203.0.113.10/32"]
  }

  assert {
    condition     = var.endpoint_public_access == false && local.public_access_cidrs == null
    error_message = "com o endpoint publico desligado a lista deveria ser omitida (null), recebido ${jsonencode(local.public_access_cidrs)}"
  }
}

run "endpoint_publico_ligado_manda_a_lista" {
  command = plan

  assert {
    # tolist nos dois lados: literal em HCL e TUPLE, e comparar com list(string) devolve
    # "LHS and RHS values are of different types" em vez de comparar.
    condition     = local.public_access_cidrs == tolist(["203.0.113.10/32"])
    error_message = "com o endpoint publico ligado a lista tem de ser mandada, recebido ${jsonencode(local.public_access_cidrs)}"
  }
}

run "cidr_malformado_e_erro" {
  command = plan

  variables {
    # Sem prefixo: passaria por uma checagem de regex ingenua e falharia so na AWS.
    public_access_cidrs = ["203.0.113.10"]
  }

  expect_failures = [var.public_access_cidrs]
}

run "role_dos_nos_tem_as_tres_policies_gerenciadas" {
  command = plan

  assert {
    condition     = length(aws_iam_role_policy_attachment.node) == 3
    error_message = "o role dos nos precisa de WorkerNode + ECR ReadOnly + CNI, recebidos ${length(aws_iam_role_policy_attachment.node)}"
  }
}
