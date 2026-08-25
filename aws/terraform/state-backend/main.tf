provider "aws" {
  region  = var.region
  profile = var.aws_profile

  default_tags {
    tags = {
      "managed-by" = "terraform"
      "layer"      = "state-backend"
    }
  }
}

# O bucket de state é bootstrap: existe UMA vez, sem região de workload, e guarda o state
# de todas as camadas e regiões. Mora numa raiz própria justamente para que nenhum
# `terraform destroy` de uma região o alcance — antes ele vivia no state da
# `network-foundation` de us-east-1, e destruir aquele hub levaria junto o mapa de tudo.
module "state_backend" {
  source = "../src/state-backend"

  bucket_name = var.bucket_name

  tags = { role = "terraform-state" }
}

# Os 6 recursos foram ADOTADOS por blocos `import` em 2026-08-25 (criados antes, quando o
# bucket ainda pertencia à network-foundation). Os blocos saíram depois do apply: são de
# uso único e falhariam num ambiente onde o bucket ainda não existe.
