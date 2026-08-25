provider "aws" {
  region  = var.region
  profile = var.aws_profile

  default_tags {
    tags = {
      "managed-by" = "terraform"
      "layer"      = "network-foundation"
    }
  }
}

module "hub_network" {
  source = "../src/network"

  name               = "${var.prefix}-hub"
  vpc_cidr           = var.hub_vpc_cidr
  availability_zones = var.availability_zones

  # Sem TGW, nada roteia pelo hub: os nós do EKS saem pelo NAT da própria VPC spoke.
  # Ligar o NAT aqui custaria ~US$ 32/mês servindo zero tráfego. Quando o TGW entrar
  # (Gap 2), revisitar.
  enable_nat_gateway = false

  tags = { role = "hub" }
}

module "state_backend" {
  source = "../src/state-backend"

  bucket_name = var.state_bucket_name

  tags = { role = "terraform-state" }
}
