terraform {
  required_version = ">= 1.15"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  backend "s3" {
    # COM região na key, ao contrário de dns/: TGW e Client VPN endpoint são regionais, e
    # um segundo hub em outra região terá a própria raiz com a própria key — mesmo padrão
    # de network-foundation/<região>/.
    key          = "connectivity/us-east-1/terraform.tfstate"
    region       = "us-east-1"
    profile      = "network"
    encrypt      = true
    use_lockfile = true
  }
}
