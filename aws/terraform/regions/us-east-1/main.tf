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

# Os providers kubernetes e helm sao configurados a partir de outputs de module.cell e aplicados no
# mesmo terraform apply: a configuracao do provider so precisa estar resolvida na hora de configura-lo,
# ja no apply. O que NAO pode e data source desses providers no plan — por isso o platform-bootstrap
# e resource, nunca data.
provider "kubernetes" {
  host                   = module.cell.cluster_endpoint
  cluster_ca_certificate = base64decode(module.cell.cluster_ca_data)

  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = ["eks", "get-token", "--cluster-name", module.cell.cluster_name, "--region", local.region, "--profile", var.aws_profile]
  }
}

# No provider helm 3.x o kubernetes deixou de ser bloco e virou atributo — note o `=`.
provider "helm" {
  kubernetes = {
    host                   = module.cell.cluster_endpoint
    cluster_ca_certificate = base64decode(module.cell.cluster_ca_data)

    exec = {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", module.cell.cluster_name, "--region", local.region, "--profile", var.aws_profile]
    }
  }
}

module "cell" {
  source = "../../src/cell"

  providers = {
    aws         = aws
    aws.network = aws.network
    kubernetes  = kubernetes
    helm        = helm
  }

  name     = "control-plane-${local.region}"
  region   = local.region
  vpc_cidr = local.cell_vpc_cidr

  base_domain        = var.base_domain
  subzone_label      = var.subzone_label
  network_account_id = var.network_account_id
  target_account_ids = var.target_account_ids

  # O hub, por referencia. Cada linha aqui e um data source que morreu do outro lado.
  hub_vpc_id                         = module.hub.vpc_id
  hub_vpc_cidr_block                 = module.hub.vpc_cidr_block
  transit_gateway_id                 = module.hub.transit_gateway_id
  hub_transit_gateway_route_table_id = module.hub.transit_gateway_route_table_id
  hub_transit_gateway_attachment_id  = module.hub.transit_gateway_attachment_id
  hub_alb_listener_arn               = module.hub.alb_listener_arn
  hub_alb_dns_name                   = module.hub.alb_dns_name
  hub_alb_zone_id                    = module.hub.alb_zone_id
}
