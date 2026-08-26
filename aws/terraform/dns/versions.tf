terraform {
  required_version = ">= 1.15"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }

    # Major 5, conferido no registry — não herdado do repo Azure pessoal, que está em
    # `~> 4.x`. O `azurerm_dns_ns_record` tem o mesmo schema nos dois (`records` como lista
    # de strings), então a subida de major não custa nada aqui.
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    # SEM região na key, ao contrário de network-foundation/<região>/: hosted zone pública é
    # recurso GLOBAL. A `region` abaixo é só onde vive o objeto de state.
    key          = "dns/terraform.tfstate"
    region       = "us-east-1"
    profile      = "network"
    encrypt      = true
    use_lockfile = true
  }
}
