terraform {
  required_version = ">= 1.15"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # O bucket de state fica na conta network, como toda raiz regional — o acesso ao
  # bucket passa pelo profile network, nunca pelo cicd.
  backend "s3" {
    key          = "ci/terraform.tfstate"
    region       = "us-east-1"
    profile      = "network"
    encrypt      = true
    use_lockfile = true
  }
}
