# Hub de us-east-1. Valores inline de propósito: região, CIDR e AZs são decisões de
# desenho documentadas (aws/docs/network/01-cidr-addressing.md), não segredo — mantê-las
# visíveis aqui vale mais que a indireção de um tfvars.
#
# CIDR: N=1 do supernet 10.0.0.0/12. N=0 é reservado à Organization.
provider "aws" {
  region  = "us-east-1"
  profile = "network"

  default_tags {
    tags = {
      "managed-by" = "terraform"
      "layer"      = "network-foundation"
    }
  }
}

module "hub_network" {
  source = "../../src/network"

  name               = "poc-hub"
  vpc_cidr           = "10.1.0.0/16"
  availability_zones = ["us-east-1a", "us-east-1b"]

  # Sem TGW, nada roteia pelo hub: os nós saem pelo NAT da própria VPC spoke. Ligar aqui
  # custaria ~US$ 32/mês servindo zero tráfego.
  enable_nat_gateway = false

  tags = { role = "hub" }
}
