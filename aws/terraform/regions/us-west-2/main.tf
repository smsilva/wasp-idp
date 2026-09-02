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
  region = "us-west-2"

  # 10.4 e 10.5, nao 10.3 e 10.4: a alocacao e por REGIAO, nao por ordem de criacao. us-east-1 ocupa
  # 10.0.0.0/14 (10.0-10.3) e us-west-2 ocupa 10.4.0.0/14 (10.4-10.7), de modo que cada regiao cabe
  # num bloco contiguo — pre-requisito de um pool regional de IPAM, que exige locale por regiao.
  # Realocado enquanto esta raiz tinha 0 recursos aplicados; com VPC de pe custaria recriar. Ver
  # docs/adr/0003-supernet-cidr-allocation.md e aws/docs/network/08-ipam.md.
  hub_vpc_cidr  = "10.4.0.0/16"
  cell_vpc_cidr = "10.5.0.0/16"

  # Duas AZs: o Client VPN associa uma target network por AZ e o NLB interno da celula fixa um IP
  # privado por AZ. UM data source por CONTA, nunca compartilhado: AZ names sao alias por-conta
  # sobre AZ IDs fisicos (ex.: "us-east-1a" pode ser um AZ ID diferente em cada conta), e o hub
  # aplica na conta network enquanto a celula aplica na cicd (provider default). Resolver os dois
  # no mesmo data source (sem provider explicito, portanto sempre na conta default) fazia o hub
  # herdar AZs resolvidas na conta ERRADA.
  hub_availability_zones  = slice(data.aws_availability_zones.network.names, 0, 2)
  cell_availability_zones = slice(data.aws_availability_zones.cell.names, 0, 2)

  # Fonte A: um ARN de var.admin_principal_arns por access entry, chaveado pelo proprio ARN — NAO
  # mudar a chave, mudar destruiria/recriaria access entries existentes.
  admin_principal_access_entries = { for arn in var.admin_principal_arns : arn => {
    principal_arn = arn
    policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
    access_scope  = "cluster"
  } }

  # Fonte B: um grupo do Identity Center (var.admin_group_ids) por access entry, chaveado pelo
  # nome do permission set. O ARN vem do data source que resolve o GroupId para a role SSO.
  admin_group_access_entries = { for name in keys(var.admin_group_ids) : name => {
    principal_arn = one(data.aws_iam_roles.admin_group[name].arns)
    policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
    access_scope  = "cluster"
  } }
}

data "aws_availability_zones" "network" {
  provider = aws.network
  state    = "available"
}

data "aws_availability_zones" "cell" {
  state = "available"
}

# Resolve o GroupId do Identity Center (var.admin_group_ids) para o ARN da role SSO provisionada
# na conta da celula. O ARN carrega o path /aws-reserved/sso.amazonaws.com/ de proposito — a doc
# do provider AWS sugere remover esse path de roles SSO, mas isso vale para o aws-auth ConfigMap
# legado; a doc de EKS access entries diz textualmente que o ARN de role PODE incluir path. Nao
# "consertar" removendo o path aqui.
data "aws_iam_roles" "admin_group" {
  for_each = var.admin_group_ids

  name_regex  = "^AWSReservedSSO_${each.key}_"
  path_prefix = "/aws-reserved/sso.amazonaws.com/"

  lifecycle {
    postcondition {
      condition     = length(self.arns) == 1
      error_message = "esperada exatamente 1 role para o permission set ${each.key} na conta da celula, encontradas ${length(self.arns)} — bootstrap do Identity Center faltando ou nome ambiguo (ver aws/docs/bootstrap/)."
    }
  }
}

module "hub" {
  source = "../../src/hub"

  providers = {
    aws = aws.network
  }

  name               = "poc-hub"
  region             = local.region
  vpc_cidr           = local.hub_vpc_cidr
  availability_zones = local.hub_availability_zones

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

  name               = "control-plane-${local.region}"
  region             = local.region
  vpc_cidr           = local.cell_vpc_cidr
  availability_zones = local.cell_availability_zones
  aws_profile        = var.aws_profile

  base_domain        = var.base_domain
  subzone_label      = var.subzone_label
  network_account_id = var.network_account_id
  target_account_ids = var.target_account_ids

  endpoint_public_access = var.endpoint_public_access
  public_access_cidrs    = var.public_access_cidrs

  # access_entries funde duas fontes de admin no formato que src/cluster espera. A politica e
  # sempre AmazonEKSClusterAdminPolicy com escopo cluster: "admin" e admin.
  access_entries = merge(local.admin_principal_access_entries, local.admin_group_access_entries)

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
