# A raiz da regiao. Dois providers, porque a regiao tem duas contas: o hub vive na `network` e a
# celula na `cicd`. O provider DEFAULT e o da celula — assim um recurso sem provider explicito cai
# na conta da celula, que e o caso comum, e o hub e sempre explicito.
#
# ADR 0007 continua valendo: recurso da conta network com ciclo de vida de celula (certificado
# wildcard, target group, listener rule) mora no modulo da celula, com provider aliasado.
provider "aws" {
  region  = local.region
  profile = var.aws_profile

  default_tags {
    tags = {
      "managed-by" = "terraform"
      "layer"      = "region"
    }
  }
}

provider "aws" {
  alias   = "network"
  region  = local.region
  profile = var.network_profile

  default_tags {
    tags = {
      "managed-by" = "terraform"
      "layer"      = "region"
    }
  }
}

locals {
  # Regiao e CIDRs sao decisao de desenho documentada em aws/docs/network/01-cidr-addressing.md,
  # nao identidade: inline aqui, como a network-foundation ja fazia. N=0 e reservado a Organization.
  region        = "us-east-1"
  hub_vpc_cidr  = "10.1.0.0/16"
  cell_vpc_cidr = "10.2.0.0/16"

  # Duas AZs: o Client VPN associa uma target network por AZ e o NLB interno da celula fixa um IP
  # privado por AZ.
  availability_zones = slice(data.aws_availability_zones.this.names, 0, 2)
}

data "aws_availability_zones" "this" {
  state = "available"
}

module "hub" {
  source = "../../src/hub"

  providers = {
    aws = aws.network
  }

  name               = "poc-hub"
  region             = local.region
  vpc_cidr           = local.hub_vpc_cidr
  availability_zones = local.availability_zones

  base_domain        = var.base_domain
  subzone_label      = var.subzone_label
  operator_group_ids = var.operator_group_ids
  spoke_account_ids  = var.spoke_account_ids
  saml_metadata_path = var.saml_metadata_path
}
