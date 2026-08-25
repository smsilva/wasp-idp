terraform {
  required_version = ">= 1.15"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  backend "s3" {
    # `bucket` entra via -backend-config: é valor real. A key traz a região, então cada
    # uma tem state próprio e destruir uma nunca toca na outra.
    key          = "network-foundation/us-west-2/terraform.tfstate"
    region       = "us-east-1"
    profile      = "network"
    encrypt      = true
    use_lockfile = true
  }
}
