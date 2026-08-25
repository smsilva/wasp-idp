locals {
  # Pod Identity exige as DUAS acoes no trust: sts:AssumeRole para assumir o role e
  # sts:TagSession para o agente carimbar a sessao com cluster/namespace/service account.
  # Faltando TagSession o pod recebe AccessDenied sem mensagem util.
  #
  # jsonencode em vez de data.aws_iam_policy_document: sob mock_provider o data source
  # devolve um valor sintetico e as assercoes sobre o conteudo do trust perderiam o sentido.
  # Aqui o documento e computado pelo proprio Terraform e o teste verifica a policy real.
  trust_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = ["sts:AssumeRole", "sts:TagSession"]
      Principal = { Service = "pods.eks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role" "this" {
  name               = var.name
  assume_role_policy = local.trust_policy

  tags = merge(var.tags, { Name = var.name })
}

resource "aws_iam_role_policy" "this" {
  count = var.policy_json == null ? 0 : 1

  name   = "${var.name}-inline"
  role   = aws_iam_role.this.id
  policy = var.policy_json
}

resource "aws_iam_role_policy_attachment" "managed" {
  for_each = toset(var.managed_policy_arns)

  role       = aws_iam_role.this.name
  policy_arn = each.value
}

resource "aws_eks_pod_identity_association" "this" {
  cluster_name    = var.cluster_name
  namespace       = var.namespace
  service_account = var.service_account_name
  role_arn        = aws_iam_role.this.arn

  tags = merge(var.tags, { Name = var.name })
}
