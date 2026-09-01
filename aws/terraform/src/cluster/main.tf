locals {
  # jsonencode em vez de data.aws_iam_policy_document: sob mock_provider o data source
  # devolve um valor sintetico e o provider rejeita o assume_role_policy no plan.
  # Mesma escolha do modulo pod-identity.
  cluster_trust_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "eks.amazonaws.com" }
    }]
  })

  node_trust_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })

  # OMITIDO (null), nao vazio, quando o endpoint publico esta desligado. A doc do provider:
  # public_access_cidrs vale "when enabled", e o Terraform "will only perform drift detection
  # of its value when present in a configuration". Presente-e-vazio com o endpoint fechado
  # seria perpetual diff: a EKS guarda 0.0.0.0/0 como default e todo plan proporia [].
  #
  # A semantica da AWS mora aqui, no modulo, onde vale para qualquer chamador — a POLITICA de
  # quem alcanca a API mora no root.
  public_access_cidrs = var.endpoint_public_access ? var.public_access_cidrs : null
}

resource "aws_iam_role" "cluster" {
  name               = "${var.name}-cluster"
  assume_role_policy = local.cluster_trust_policy

  tags = merge(var.tags, { Name = "${var.name}-cluster" })
}

resource "aws_iam_role_policy_attachment" "cluster" {
  role       = aws_iam_role.cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

# Um unico role compartilhado por todos os node groups. Permissoes por workload nao vem
# daqui — vem de Pod Identity, que e o ponto da camada.
resource "aws_iam_role" "node" {
  name               = "${var.name}-node"
  assume_role_policy = local.node_trust_policy

  tags = merge(var.tags, { Name = "${var.name}-node" })
}

resource "aws_iam_role_policy_attachment" "node" {
  for_each = toset([
    "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
    "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
    "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",
  ])

  role       = aws_iam_role.node.name
  policy_arn = each.value
}

resource "aws_eks_cluster" "this" {
  name     = var.name
  version  = var.kubernetes_version
  role_arn = aws_iam_role.cluster.arn

  access_config {
    authentication_mode                         = "API"
    bootstrap_cluster_creator_admin_permissions = true
  }

  vpc_config {
    subnet_ids              = var.subnet_ids
    endpoint_public_access  = var.endpoint_public_access
    endpoint_private_access = var.endpoint_private_access
    public_access_cidrs     = local.public_access_cidrs
  }

  tags = merge(var.tags, { Name = var.name })

  depends_on = [aws_iam_role_policy_attachment.cluster]
}

resource "aws_eks_access_entry" "this" {
  for_each = var.access_entries

  cluster_name  = aws_eks_cluster.this.name
  principal_arn = each.value.principal_arn

  tags = merge(var.tags, { Name = "${var.name}-${each.key}" })
}

resource "aws_eks_access_policy_association" "this" {
  for_each = var.access_entries

  cluster_name  = aws_eks_cluster.this.name
  principal_arn = each.value.principal_arn
  policy_arn    = each.value.policy_arn

  access_scope {
    type = each.value.access_scope
  }

  depends_on = [aws_eks_access_entry.this]
}

# So a BASE de identidade mora aqui: o agent que serve as credenciais de Pod Identity. Quem
# CONSOME Pod Identity nao pode nascer neste modulo — o cluster nao enxerga as associations,
# que sao criadas pelo chamador a partir do cluster_name deste modulo (depender delas daqui
# seria ciclo). O addon do EBS CSI, que consome, mora em src/cell com depends_on explicito;
# ver o comentario la e aws/CLAUDE.md, "race de Pod Identity do EBS CSI".
#
# Sem addon_version: a AWS escolhe a compativel com a versao do cluster.
resource "aws_eks_addon" "this" {
  for_each = toset(["eks-pod-identity-agent"])

  cluster_name                = aws_eks_cluster.this.name
  addon_name                  = each.value
  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"

  tags = merge(var.tags, { Name = "${var.name}-${each.value}" })
}
