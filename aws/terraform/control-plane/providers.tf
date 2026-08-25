provider "aws" {
  region  = var.region
  profile = var.aws_profile

  default_tags {
    tags = {
      "managed-by" = "terraform"
      "layer"      = "control-plane"
    }
  }
}

# Somente leitura, para descobrir a VPC hub. A camada 2 nao escreve nada na conta network.
provider "aws" {
  alias   = "network"
  region  = var.region
  profile = var.network_profile
}

# Configurar os providers kubernetes e helm a partir de outputs do modulo do cluster e
# aplicar tudo num unico terraform apply funciona: o Terraform so precisa da configuracao
# resolvida na hora de configurar o provider, ja no apply. O que NAO pode e um data source
# desses providers no plan — por isso o platform-bootstrap e um resource, nunca um data.
# Mesmo padrao de examples/cluster_argocd_ingress_istio no repo azure-kubernetes.
provider "kubernetes" {
  host                   = module.cluster.cluster_endpoint
  cluster_ca_certificate = base64decode(module.cluster.cluster_ca_data)

  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = ["eks", "get-token", "--cluster-name", module.cluster.cluster_name, "--region", var.region, "--profile", var.aws_profile]
  }
}

# No provider helm 3.x o kubernetes deixou de ser bloco e virou atributo — note o `=`.
provider "helm" {
  kubernetes = {
    host                   = module.cluster.cluster_endpoint
    cluster_ca_certificate = base64decode(module.cluster.cluster_ca_data)

    exec = {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", module.cluster.cluster_name, "--region", var.region, "--profile", var.aws_profile]
    }
  }
}
