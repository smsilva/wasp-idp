# Subzona delegada por ambiente, e a delegação é CÓDIGO — não passo manual no portal.
#
# Por que raiz própria, e não dentro de connectivity/: connectivity é destruído toda noite,
# e uma hosted zone recriada nasce com name servers NOVOS. Com a delegação automatizada isso
# até se corrigiria sozinho, mas a propagação de NS não é instantânea e o edge ficaria
# intermitente sem motivo. Zona é T0: ~US$ 0,50/mês, prevent_destroy, e a automação existe
# para quando a recriação FOR necessária, não como licença para recriar.
#
# Ganho de permissão: a subzona é a fronteira de blast radius do DNS. O external-dns dentro
# do cluster recebe acesso só a ela e não alcança o apex — separação que não existiria com o
# domínio inteiro delegado.

locals {
  subzone_fqdn = "${var.subzone_label}.${var.base_domain}"
}

provider "aws" {
  region  = "us-east-1"
  profile = var.network_profile

  default_tags {
    tags = {
      "managed-by" = "terraform"
      "layer"      = "dns"
    }
  }
}

provider "azurerm" {
  features {}

  subscription_id = var.azure_subscription_id
}

resource "aws_route53_zone" "subzone" {
  name = local.subzone_fqdn

  comment = "Subzona delegada do apex no Azure DNS. Fronteira de permissao do external-dns."

  # Destruir esta zona é perder os name servers e quebrar a delegação da pai até a
  # propagação do NS novo. Nunca é a intenção — ao contrário do T1, que é destruído de
  # propósito todo dia.
  lifecycle {
    prevent_destroy = true
  }
}

# A delegação, do lado Azure, cabeada direto nos name servers que a AWS acabou de dar. Sem
# copiar e colar valor entre clouds, e destruir esta raiz remove o NS junto — sem resíduo
# apontando para name servers que não existem mais.
resource "azurerm_dns_ns_record" "delegation" {
  count = var.manage_delegation ? 1 : 0

  name                = var.subzone_label
  zone_name           = var.base_domain
  resource_group_name = var.azure_dns_resource_group

  # TTL curto de propósito: é o que permite recriar a subzona e ver a delegação nova pegar
  # em minutos, em vez de horas.
  ttl = 300

  records = aws_route53_zone.subzone.name_servers
}
