locals {
  install_external_secrets = true
  install_argocd           = true
  install_crossplane       = true
  install_argocd_oidc      = false # exige o client secret ja no Secrets Manager
  install_app_of_apps      = false # entregue por GitOps, fora do Terraform

  tags = { role = "control-plane" }
}

# A VPC hub e lida pela API da AWS, nao pelo state da camada 1. A camada 2 depende do
# recurso existir, nao do arquivo de state — se a camada 1 mudar de backend ou de chave,
# isto continua valendo. Custo: exige um provider aliasado e credencial de leitura na
# conta network.
data "aws_vpc" "hub" {
  provider = aws.network

  filter {
    name   = "tag:Name"
    values = [var.hub_vpc_name]
  }
}

module "network" {
  source = "../src/network"

  name               = var.name
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
  enable_nat_gateway = var.enable_nat_gateway
  tags               = local.tags
}

module "cluster" {
  source = "../src/cluster"

  name               = var.name
  kubernetes_version = var.kubernetes_version
  subnet_ids         = module.network.control_plane_subnet_ids
  access_entries     = var.access_entries
  tags               = local.tags
}

module "nodegroup" {
  source = "../src/nodegroup"

  cluster_name  = module.cluster.cluster_name
  node_role_arn = module.cluster.node_role_arn
  subnet_ids    = module.network.private_subnet_ids
  tags          = local.tags
}

module "pod_identity_ebs_csi" {
  source = "../src/pod-identity"

  name                 = "${var.name}-ebs-csi"
  cluster_name         = module.cluster.cluster_name
  namespace            = "kube-system"
  service_account_name = "ebs-csi-controller-sa"
  managed_policy_arns  = ["arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"]
  tags                 = local.tags
}

module "pod_identity_eso" {
  source = "../src/pod-identity"

  name                 = "${var.name}-external-secrets"
  cluster_name         = module.cluster.cluster_name
  namespace            = "external-secrets"
  service_account_name = "external-secrets"
  policy_json = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret",
      ]
      Resource = "*"
    }]
  })
  tags = local.tags
}

# Esta e a razao de ser da camada: o Crossplane deixa de depender da access key de longa
# duracao do crossplane-poc e passa a assumir os roles das contas alvo por Pod Identity.
module "pod_identity_crossplane" {
  source = "../src/pod-identity"

  name                 = "${var.name}-crossplane"
  cluster_name         = module.cluster.cluster_name
  namespace            = "crossplane-system"
  service_account_name = "crossplane"
  policy_json = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["sts:AssumeRole", "sts:TagSession"]
      Resource = [for account_id in var.target_account_ids : "arn:aws:iam::${account_id}:role/crossplane-*"]
    }]
  })
  tags = local.tags
}

# A association de Pod Identity vem ANTES do release: se o pod subir sem ela, falha em
# AccessDenied e fica em CrashLoop ate um restart manual.
module "external_secrets" {
  source = "../src/helm/modules/external-secrets"
  count  = local.install_external_secrets ? 1 : 0

  depends_on = [
    module.nodegroup,
    module.pod_identity_eso,
  ]
}

module "argo_cd" {
  source = "../src/helm/modules/argo-cd"
  count  = local.install_argocd ? 1 : 0

  oidc_enabled = local.install_argocd_oidc

  depends_on = [module.external_secrets]
}

module "crossplane" {
  source = "../src/helm/modules/crossplane"
  count  = local.install_crossplane ? 1 : 0

  depends_on = [
    module.nodegroup,
    module.pod_identity_crossplane,
  ]
}

# Fronteira com o GitOps. Tudo que o app-of-apps precisa saber sobre esta celula esta
# aqui — nenhum manifesto do GitOps carrega id de conta ou de VPC hardcoded.
resource "kubernetes_config_map_v1" "platform_bootstrap" {
  metadata {
    name      = "platform-bootstrap"
    namespace = "crossplane-system"
  }

  data = {
    region            = var.region
    clusterName       = module.cluster.cluster_name
    hubVpcId          = data.aws_vpc.hub.id
    spokeSubnetIds    = join(",", module.network.private_subnet_ids)
    crossplaneRoleArn = module.pod_identity_crossplane.role_arn
    networkAccountId  = var.network_account_id
    targetAccountIds  = join(",", var.target_account_ids)
  }

  depends_on = [module.crossplane]
}
