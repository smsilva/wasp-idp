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
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_org}/${var.github_repo}:ref:refs/heads/*"
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
