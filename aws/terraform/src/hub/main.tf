# src/hub — VPC hub, TGW, RAM, Client VPN e ALB de ingress num modulo so. Colapsa o que eram as
# camadas network-foundation/ (01) e connectivity/ (03). O provider vem da RAIZ (a conta network),
# passado por `providers = { aws = aws.network }`; este modulo nao declara provider.
#
# Os quatro data sources que a connectivity/ usava para achar a VPC hub e suas subnets por tag
# (data.aws_vpc.hub, data.aws_subnets.*, data.aws_route_table.*) DESAPARECEM: aqui a VPC e do
# proprio modulo, e module.network ja expoe tudo aquilo como output. So a subzona do Route 53
# continua data source — ela pertence a raiz dns/, externa a este modulo.

locals {
  # Supernet inteira, uma rota so. Rota e TOPOLOGIA — o que existe e e alcancavel pela malha; nao
  # cresce com spoke. O que cresce com spoke e authorization rule, que e POLITICA (quem pode).
  subzone_fqdn = "${var.subzone_label}.${var.base_domain}"

  # Certificado DEFAULT do listener :443. Wildcard cobre um nivel so, entao este casa
  # `app.nonprod.<dominio>` e NAO casa `app.<id>.nonprod.<dominio>` — o certificado de cada celula
  # entra por SNI a partir do state da propria celula. Existe para o listener nascer valido e
  # responder 404 a host desconhecido, nao para servir trafego.
  alb_default_fqdn = "*.${local.subzone_fqdn}"

  # IAM e Route 53 nao sao regionais. Dois hubs em duas regioes da MESMA Organization disputam
  # estes dois nomes: o SAML provider falha com EntityAlreadyExists (barulhento, tudo bem) e o
  # record do Route 53 e sobrescrito em silencio (o modo ruim de descobrir). A regiao entra no
  # nome para separa-los.
  regional_name = "${var.name}-${var.region}"

  # O nome do certificado nao precisa casar com o hostname do endpoint: o client usa
  # `remote-cert-tls server`, que confere extended key usage, nao nome. Um nome sob a subzona e o
  # que permite validar por DNS na zona que ja e nossa — e a regiao o torna unico entre hubs.
  vpn_fqdn = "vpn.${var.region}.${local.subzone_fqdn}"

  tags = merge(var.tags, { role = "hub" })
}

# A VPC hub e suas subnets, agora do proprio grafo — nao mais descobertas por tag.
module "network" {
  source = "../network"

  name               = var.name
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones

  # Sem TGW nada roteia pelo hub: os nos saem pelo NAT da propria VPC da celula. Ligar aqui
  # custaria ~US$ 32/mes servindo zero trafego. Ha teste cobrindo a ausencia do EIP.
  enable_nat_gateway = false

  tags = local.tags
}

# A subzona que a raiz `dns/` criou e delegou. Lida por nome, nao por id: o id muda se a zona for
# recriada, o nome nao. Unico data source que sobrevive: pertence a uma raiz externa.
data "aws_route53_zone" "subzone" {
  name         = local.subzone_fqdn
  private_zone = false
}

# --------------------------------------------------------------------------------------
# Transit Gateway
# --------------------------------------------------------------------------------------

# O isolamento por tenant comeca aqui, nos dois `disable`. O TGW nasce com association e
# propagation default LIGADOS: com eles, todo attachment aprende todo mundo e spoke fala com spoke
# sem ninguem ter pedido. Desligados, cada attachment so alcanca o que uma route table explicita
# disser — spoke nasce isolada, e habilitar e aditivo e visivel em diff.
resource "aws_ec2_transit_gateway" "hub" {
  description = "Hub de transito de ${var.region}. Association e propagation default desligados de proposito."

  default_route_table_association = "disable"
  default_route_table_propagation = "disable"

  dns_support = "enable"

  tags = merge(local.tags, { Name = "${var.name}-tgw" })
}

# Route table do proprio hub. As de tenant (`tgw-rt-<spoke>`) NAO nascem aqui: o ciclo de vida
# delas e o do spoke, entao moram no state do spoke mesmo sendo recurso da conta network.
resource "aws_ec2_transit_gateway_route_table" "hub" {
  transit_gateway_id = aws_ec2_transit_gateway.hub.id

  tags = merge(local.tags, { Name = "${var.name}-tgw-rt-hub" })
}

# --------------------------------------------------------------------------------------
# RAM — pre-requisito de attachment cross-conta
# --------------------------------------------------------------------------------------

resource "aws_ram_resource_share" "tgw" {
  name = "${var.name}-tgw"

  allow_external_principals = false

  tags = merge(local.tags, { Name = "${var.name}-tgw-share" })
}

resource "aws_ram_resource_association" "tgw" {
  resource_arn       = aws_ec2_transit_gateway.hub.arn
  resource_share_arn = aws_ram_resource_share.tgw.arn
}

resource "aws_ram_principal_association" "spoke" {
  for_each = toset(var.spoke_account_ids)

  principal          = each.value
  resource_share_arn = aws_ram_resource_share.tgw.arn
}

# --------------------------------------------------------------------------------------
# Attachment da propria VPC hub — sem ele, o que chega pelo tunel na subnet privada nao tem como
# sair para o TGW.
# --------------------------------------------------------------------------------------

resource "aws_ec2_transit_gateway_vpc_attachment" "hub" {
  vpc_id     = module.network.vpc_id
  subnet_ids = module.network.private_subnet_ids

  transit_gateway_id = aws_ec2_transit_gateway.hub.id

  transit_gateway_default_route_table_association = false
  transit_gateway_default_route_table_propagation = false

  tags = merge(local.tags, { Name = "${var.name}-tgw-attachment" })
}

resource "aws_ec2_transit_gateway_route_table_association" "hub" {
  transit_gateway_attachment_id  = aws_ec2_transit_gateway_vpc_attachment.hub.id
  transit_gateway_route_table_id = aws_ec2_transit_gateway_route_table.hub.id
}

# Uma rota so, para a supernet inteira, para sempre: rota e TOPOLOGIA e nao cresce por spoke — quem
# cresce por spoke e a authorization rule (politica), nao esta rota. A route table privada agora e
# output do proprio modulo network, nao mais data source por tag.
resource "aws_route" "hub_to_tgw" {
  route_table_id         = module.network.private_route_table_id
  destination_cidr_block = var.supernet
  transit_gateway_id     = aws_ec2_transit_gateway.hub.id

  depends_on = [aws_ec2_transit_gateway_vpc_attachment.hub]
}

# A route table PUBLICA do hub, onde vive o ALB de ingress — e por isso que ela tambem precisa da
# rota. Sem ela o health check do ALB para os enderecos fixos do NLB da celula nao tem caminho de
# ida, e o sintoma e target `unhealthy`/`Request timed out` com o target group DA SPOKE `healthy`.
resource "aws_route" "hub_public_to_tgw" {
  route_table_id         = module.network.public_route_table_id
  destination_cidr_block = var.supernet
  transit_gateway_id     = aws_ec2_transit_gateway.hub.id

  depends_on = [aws_ec2_transit_gateway_vpc_attachment.hub]
}

# --------------------------------------------------------------------------------------
# Certificado do endpoint
# --------------------------------------------------------------------------------------

# Publico do ACM, validado por DNS na subzona — nao autoassinado importado. Nenhuma chave privada
# em state nem em disco; rotacao automatica que o Client VPN acompanha.
resource "aws_acm_certificate" "vpn" {
  domain_name       = local.vpn_fqdn
  validation_method = "DNS"

  tags = merge(local.tags, { Name = local.vpn_fqdn })

  lifecycle {
    create_before_destroy = true
  }
}

# UM registro, indexado — as chaves de um for_each sobre domain_validation_options viriam de
# atributo computado. Um dominio, nenhum SAN, um elemento.
resource "aws_route53_record" "vpn_validation" {
  zone_id = data.aws_route53_zone.subzone.zone_id
  name    = tolist(aws_acm_certificate.vpn.domain_validation_options)[0].resource_record_name
  type    = tolist(aws_acm_certificate.vpn.domain_validation_options)[0].resource_record_type
  records = [tolist(aws_acm_certificate.vpn.domain_validation_options)[0].resource_record_value]

  ttl             = 60
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "vpn" {
  certificate_arn         = aws_acm_certificate.vpn.arn
  validation_record_fqdns = [aws_route53_record.vpn_validation.fqdn]
}

# --------------------------------------------------------------------------------------
# Client VPN
# --------------------------------------------------------------------------------------

# O provider SAML liga o endpoint ao Identity Center. O metadata NAO e gerado por Terraform: a API
# CreateApplication so cria aplicacoes OAuth 2.0 customizadas, entao a aplicacao SAML e passo de
# console e o XML dela entra por arquivo. O NOME carrega a regiao: IAM e global, e dois hubs na
# mesma conta colidiriam com EntityAlreadyExists.
resource "aws_iam_saml_provider" "client_vpn" {
  name                   = "${local.regional_name}-client-vpn"
  saml_metadata_document = file(var.saml_metadata_path)

  tags = merge(local.tags, { Name = "${local.regional_name}-client-vpn" })
}

resource "aws_ec2_client_vpn_endpoint" "hub" {
  description = "Acesso de manutencao a rede privada, autenticado pelo Identity Center."

  server_certificate_arn = aws_acm_certificate_validation.vpn.certificate_arn
  client_cidr_block      = var.client_cidr_block

  split_tunnel = true

  vpc_id = module.network.vpc_id

  authentication_options {
    type              = "federated-authentication"
    saml_provider_arn = aws_iam_saml_provider.client_vpn.arn
  }

  connection_log_options {
    enabled = false
  }

  tags = merge(local.tags, { Name = "${var.name}-client-vpn" })
}

# A associacao tira o endpoint de `pending-associate` e o torna conectavel. Uma por AZ, em subnet
# PRIVADA. `count` e nao `for_each`: o id de subnet e produto de apply (subnet criada pelo
# module.network), entao `toset(private_subnet_ids)` teria chaves desconhecidas no plan. O
# COMPRIMENTO do splat e conhecido — e igual a `length(var.availability_zones)` —, entao `count`
# funciona e a chave e o proprio indice.
resource "aws_ec2_client_vpn_network_association" "hub" {
  count = length(module.network.private_subnet_ids)

  client_vpn_endpoint_id = aws_ec2_client_vpn_endpoint.hub.id
  subnet_id              = module.network.private_subnet_ids[count.index]
}

# Uma rota, o supernet inteiro. A local da VPC hub a AWS acrescenta sozinha na associacao — as duas
# convivem por prefixo mais longo.
resource "aws_ec2_client_vpn_route" "supernet" {
  count = length(module.network.private_subnet_ids)

  client_vpn_endpoint_id = aws_ec2_client_vpn_endpoint.hub.id
  destination_cidr_block = var.supernet
  target_vpc_subnet_id   = module.network.private_subnet_ids[count.index]

  depends_on = [aws_ec2_client_vpn_network_association.hub]
}

# A politica de quem alcanca o que. Uma rule por grupo. `authorize_all_groups` NUNCA entra aqui:
# com ele, todo mundo que autentica alcanca o CIDR e a distincao por grupo desaparece.
resource "aws_ec2_client_vpn_authorization_rule" "operators" {
  for_each = var.manage_authorization ? toset(var.operator_group_ids) : toset([])

  client_vpn_endpoint_id = aws_ec2_client_vpn_endpoint.hub.id
  target_network_cidr    = var.supernet
  access_group_id        = each.value
}

# --------------------------------------------------------------------------------------
# Ingress do hub — ALB publico
# --------------------------------------------------------------------------------------

# O ALB vive no hub e nao numa camada permanente porque sem TGW ele nao alcanca spoke nenhuma — e um
# listener servindo 404. O ciclo de vida dele e o do plano de conectividade.
resource "aws_security_group" "alb" {
  name        = "${var.name}-ingress-alb"
  description = "Public ingress ALB: accepts HTTPS from the internet, reaches spokes only"
  vpc_id      = module.network.vpc_id

  tags = merge(local.tags, { Name = "${var.name}-ingress-alb" })

  lifecycle {
    create_before_destroy = true
  }
}

# 0.0.0.0/0 na ENTRADA e o valor certo aqui, e e o oposto do NLB da spoke. Este e o ponto de
# entrada publico unico do desenho.
resource "aws_vpc_security_group_ingress_rule" "alb_https" {
  security_group_id = aws_security_group.alb.id
  description       = "Public HTTPS"

  cidr_ipv4   = "0.0.0.0/0"
  ip_protocol = "tcp"
  from_port   = 443
  to_port     = 443
}

resource "aws_vpc_security_group_ingress_rule" "alb_http_redirect" {
  security_group_id = aws_security_group.alb.id
  description       = "Public HTTP, redirected to HTTPS"

  cidr_ipv4   = "0.0.0.0/0"
  ip_protocol = "tcp"
  from_port   = 80
  to_port     = 80
}

# A SAIDA e o que contem o blast radius: o supernet cobre qualquer spoke pelo TGW, e nada alem.
# Porta 80 porque o trecho hub->spoke e HTTP puro de proposito.
resource "aws_vpc_security_group_egress_rule" "alb_to_spokes" {
  security_group_id = aws_security_group.alb.id
  description       = "Reach the internal ingress NLB of any spoke"

  cidr_ipv4   = var.supernet
  ip_protocol = "tcp"
  from_port   = 80
  to_port     = 80
}

resource "aws_lb" "hub" {
  name               = "${var.name}-ingress"
  load_balancer_type = "application"
  internal           = false
  ip_address_type    = "ipv4"
  security_groups    = [aws_security_group.alb.id]

  # As PUBLICAS. Um internet-facing em subnet privada nao tem rota para o IGW e falha em silencio.
  subnets = module.network.public_subnet_ids

  tags = merge(local.tags, { Name = "${var.name}-ingress" })
}

# Certificado default do listener. Mesmo padrao do certificado do Client VPN: publico do ACM,
# validado por DNS na subzona que ja e nossa.
resource "aws_acm_certificate" "alb" {
  domain_name       = local.alb_default_fqdn
  validation_method = "DNS"

  # `*` NAO e caractere valido em valor de tag do ACM — o servico exige
  # `([\p{L}\p{Z}\p{N}_.:/=+\-@]*)`, mais restrito que a tag comum de EC2, e recusa o apply com
  # ValidationException apontando um indice de tag. A validacao e server-side, mas o VALOR e
  # conhecido em tempo de plan — dai a assercao de regressao nos testes.
  tags = merge(local.tags, { Name = "wildcard.${local.subzone_fqdn}" })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "alb_validation" {
  zone_id = data.aws_route53_zone.subzone.zone_id
  name    = tolist(aws_acm_certificate.alb.domain_validation_options)[0].resource_record_name
  type    = tolist(aws_acm_certificate.alb.domain_validation_options)[0].resource_record_type
  records = [tolist(aws_acm_certificate.alb.domain_validation_options)[0].resource_record_value]

  ttl             = 60
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "alb" {
  certificate_arn         = aws_acm_certificate.alb.arn
  validation_record_fqdns = [aws_route53_record.alb_validation.fqdn]
}

# O listener compartilhado. Um so, por SNI: cada celula anexa o proprio certificado e casa o
# proprio host por listener rule. O certificate_arn vem do VALIDATION, nao do certificate.
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.hub.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate_validation.alb.certificate_arn

  # Host que nao casa nenhuma rule recebe 404 explicito. Um 503 nao distinguiria "host
  # desconhecido" de "backend caido".
  default_action {
    type = "fixed-response"

    fixed_response {
      content_type = "text/plain"
      message_body = "no route for this host"
      status_code  = "404"
    }
  }
}

resource "aws_lb_listener" "http_redirect" {
  load_balancer_arn = aws_lb.hub.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"

    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}
