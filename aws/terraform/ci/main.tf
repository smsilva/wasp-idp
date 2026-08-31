provider "aws" {
  region  = var.region
  profile = var.cicd_profile

  default_tags {
    tags = {
      "managed-by" = "terraform"
      "layer"      = "ci"
    }
  }
}

provider "aws" {
  alias   = "network"
  region  = var.region
  profile = var.network_profile

  default_tags {
    tags = {
      "managed-by" = "terraform"
      "layer"      = "ci"
    }
  }
}

locals {
  # jsonencode em vez de data.aws_iam_policy_document: sob mock_provider o data source
  # devolve valor sintetico e a asercao do teste sobre aud/sub perderia o sentido — mesmo
  # motivo documentado em src/pod-identity/main.tf.
  cicd_trust_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRoleWithWebIdentity"
      Principal = { Federated = aws_iam_openid_connect_provider.github.arn }
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          # Formato qualificado por ID (owner@owner_id/repo@repo_id), nao repo:<owner>/<repo>:... —
          # o dono ou o repositorio ja foi renomeado, e o GitHub passa a emitir o claim `sub`
          # sempre com os IDs numericos imutaveis apos isso, mesmo tendo voltado ao nome atual.
          # Confirmado num AssumeRoleWithWebIdentity real via CloudTrail. Ver ci/README.md.
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_org}@${var.github_owner_id}/${var.github_repo}@${var.github_repo_id}:ref:refs/heads/*"
        }
      }
    }]
  })
}

# thumbprint_list omitido de proposito: a AWS valida o endpoint JWKS pela propria
# biblioteca de CAs raiz confiaveis, e a doc do provider e explicita que, para o GitHub,
# qualquer thumbprint configurado "e retido na configuracao mas nao usado para
# verificacao". Fixar aqui e a armadilha classica de CI que quebra na rotacao do
# certificado, por zero seguranca a mais — ver ci/README.md.
resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

resource "aws_iam_role" "cicd" {
  name               = var.role_name
  assume_role_policy = local.cicd_trust_policy

  # 6h, o teto de duracao de um job em runner hospedado pelo GitHub — passar disso nao
  # compra nada (o runner e morto antes) e so alarga a janela de exposicao da credencial.
  #
  # Por que precisa ser explicito: a sessao da cicd nasce de AssumeRoleWithWebIdentity, cujo
  # DurationSeconds vai de 900s ate o MaxSessionDuration DA ROLE (doc da STS) — o teto de 1h
  # do role chaining NAO se aplica a ela. Com o default de 3600 o apply morria em 1h sem
  # caminho de renovacao: o token OIDC do GitHub (~5 min) ja nao existe mais a essa altura.
  # Com 6h aqui, a sessao da network (essa sim capada em 1h por ser chaining) e re-derivada
  # sozinha pelo SDK a partir da cicd, quantas vezes for preciso. Ver ci/README.md.
  max_session_duration = 21600
}

locals {
  network_trust_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { AWS = aws_iam_role.cicd.arn }
    }]
  })
}

resource "aws_iam_role" "network" {
  provider           = aws.network
  name               = var.role_name
  assume_role_policy = local.network_trust_policy
}

# PowerUserAccess + inline de IAM: fallback aceito para as duas roles nesta PoC —
# decisao explicita da spec aprovada em 2026-08-31. Derivar o escopo fino por modulo
# (VPC/EKS/ELB/Route53/Secrets Manager de um lado, VPC/TGW/Client VPN/ACM/RAM/Route53
# do outro) fica registrado como trabalho futuro, nao esquecimento — ver ci/README.md.
resource "aws_iam_role_policy_attachment" "cicd_power_user" {
  role       = aws_iam_role.cicd.name
  policy_arn = "arn:aws:iam::aws:policy/PowerUserAccess"
}

resource "aws_iam_role_policy_attachment" "network_power_user" {
  provider   = aws.network
  role       = aws_iam_role.network.name
  policy_arn = "arn:aws:iam::aws:policy/PowerUserAccess"
}

# PowerUserAccess exclui gestao de IAM por desenho da AWS — os dois modulos criam
# roles (cluster, node group, pod identities, SAML provider do Client VPN), entao as
# duas roles precisam de um inline cobrindo isso, alem do sts:AssumeRole encadeado.
resource "aws_iam_role_policy" "cicd_iam_and_assume" {
  name = "${var.role_name}-iam-and-assume"
  role = aws_iam_role.cicd.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "IamForClusterAndPodIdentity"
        Effect = "Allow"
        Action = [
          "iam:CreateRole",
          "iam:DeleteRole",
          "iam:GetRole",
          "iam:TagRole",
          "iam:UntagRole",
          "iam:PutRolePolicy",
          "iam:DeleteRolePolicy",
          "iam:GetRolePolicy",
          # ListRolePolicies/ListAttachedRolePolicies faltavam na primeira versao: o provider AWS
          # chama as duas (inline e managed) ao ler/atualizar uma role existente, e sem elas o
          # plan/apply falha com AccessDenied mesmo tendo PutRolePolicy/AttachRolePolicy —
          # confirmado em dois applies reais (module.cluster.aws_iam_role.cluster e as 5 roles
          # de Pod Identity).
          "iam:ListRolePolicies",
          "iam:ListAttachedRolePolicies",
          "iam:AttachRolePolicy",
          "iam:DetachRolePolicy",
          "iam:PassRole",
          "iam:CreateServiceLinkedRole",
          # Terceiro gap descoberto no mesmo apply real: ao DELETAR uma role (replace ou
          # destroy), o provider chama ListInstanceProfilesForRole para checar instance
          # profiles anexados antes de apagar — gotcha ja documentado em aws/CLAUDE.md para o
          # bootstrap-iam-policy.json do usuario crossplane-poc, repetido aqui.
          "iam:ListInstanceProfilesForRole",
        ]
        Resource = "*"
      },
    ]
  })
}

resource "aws_iam_role_policy" "cicd_assume_network" {
  name = "${var.role_name}-assume-network"
  role = aws_iam_role.cicd.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "AssumeNetworkRole"
      Effect   = "Allow"
      Action   = "sts:AssumeRole"
      Resource = aws_iam_role.network.arn
    }]
  })
}

resource "aws_iam_role_policy" "network_iam_saml" {
  provider = aws.network
  name     = "${var.role_name}-iam-saml"
  role     = aws_iam_role.network.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "SamlProviderForClientVpn"
      Effect = "Allow"
      Action = [
        "iam:CreateSAMLProvider",
        "iam:DeleteSAMLProvider",
        "iam:GetSAMLProvider",
        "iam:UpdateSAMLProvider",
        "iam:TagSAMLProvider",
        "iam:ListSAMLProviders",
      ]
      Resource = "*"
    }]
  })
}

output "cicd_role_arn" {
  description = "ARN da role assumida via OIDC do GitHub. Configurar como variable CICD_ROLE_ARN no repositorio GitHub."
  value       = aws_iam_role.cicd.arn
}

output "network_role_arn" {
  description = "ARN da role assumida por encadeamento a partir da cicd. Configurar como variable NETWORK_ROLE_ARN no repositorio GitHub."
  value       = aws_iam_role.network.arn
}
