terraform {
  required_version = ">= 1.15"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Auto-hospedado: o state desta raiz mora no bucket que ela mesma gerencia. Não é
  # circular na prática — o bucket já existe quando esta raiz roda (foi criado pela
  # `network-foundation` e adotado por `import`), e se um dia precisar nascer do zero, o
  # caminho é o mesmo de qualquer bootstrap: state local, apply, `init -migrate-state`.
  backend "s3" {
    key          = "state-backend/terraform.tfstate"
    region       = "us-east-1"
    profile      = "network"
    encrypt      = true
    use_lockfile = true
  }
}
