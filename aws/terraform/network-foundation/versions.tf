terraform {
  required_version = ">= 1.15"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  backend "s3" {
    # `bucket` fica fora do arquivo porque é valor real — entra via -backend-config no init.
    key    = "network-foundation/terraform.tfstate"
    region = "us-east-1"
    # O profile precisa estar aqui: o backend é inicializado ANTES de o provider ser
    # configurado, então ele não herda `profile` do bloco provider.
    profile = "network"
    encrypt = true
    # Lock nativo do backend S3 (estável desde o Terraform 1.11) — dispensa a tabela
    # DynamoDB do padrão antigo.
    use_lockfile = true
  }
}
