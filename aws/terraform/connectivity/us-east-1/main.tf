# Camada 3 — conectividade do hub: TGW e o caminho de acesso de manutenção.
#
# Raiz SEPARADA de network-foundation/ de propósito: aquela é deliberadamente de custo zero,
# e isso é propriedade de segurança — pode ficar ligada sem ninguém pensar. Esta cobra por
# hora (~US$ 0,15/h) e é destruída ao fim do dia. Misturar as duas apagaria a distinção.
#
# Nível T1 do plano: SEM prevent_destroy em nada aqui. A proteção contra destruir por engano
# é o script `destroy` dizer em voz alta o que se perde, não o Terraform recusar.

locals {
  name = "poc-hub"

  # Supernet inteira, uma rota só. Rota é TOPOLOGIA — o que existe e é alcançável pela
  # malha; não cresce com spoke. O que cresce com spoke é authorization rule, que é
  # POLÍTICA (quem pode).
  supernet = "10.0.0.0/12"

  subzone_fqdn = "${var.subzone_label}.${var.base_domain}"

  # Certificado DEFAULT do listener :443. Wildcard cobre um nível só, então este casa
  # `app.nonprod.<domínio>` e NÃO casa `app.<id>.nonprod.<domínio>` — o certificado de cada
  # célula entra por SNI (aws_lb_listener_certificate) a partir do state da própria célula.
  # Ele existe para o listener nascer válido e responder 404 a host desconhecido, não para
  # servir tráfego.
  alb_default_fqdn = "*.${local.subzone_fqdn}"

  # O nome do certificado não precisa casar com o hostname do endpoint: o client usa
  # `remote-cert-tls server`, que confere extended key usage, não nome. Um nome sob a
  # subzona é o que permite validar por DNS na zona que já é nossa.
  vpn_fqdn = "vpn.${local.subzone_fqdn}"

  tags = { role = "hub" }
}

provider "aws" {
  region  = "us-east-1"
  profile = var.aws_profile

  default_tags {
    tags = {
      "managed-by" = "terraform"
      "layer"      = "connectivity"
    }
  }
}

# A VPC hub e suas subnets privadas vêm da API, não do state da camada 1 — mesmo padrão da
# camada 4. Depender do recurso existir, e não do arquivo de state, sobrevive a mudança de
# backend ou de key do outro lado.
data "aws_vpc" "hub" {
  filter {
    name   = "tag:Name"
    values = ["${local.name}-vpc"]
  }
}

data "aws_subnets" "hub_private" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.hub.id]
  }

  filter {
    name   = "tag:Name"
    values = ["${local.name}-private-*"]
  }
}

# As públicas, para o ALB de ingress. Mesmo padrão do irmão acima, de propósito: a raiz
# network-foundation/ também expõe `hub_public_subnet_ids` como output, mas ler o state dela
# amarraria esta camada ao backend e à key do outro lado. Descobrir por tag depende só de o
# recurso existir.
data "aws_subnets" "hub_public" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.hub.id]
  }

  filter {
    name   = "tag:Name"
    values = ["${local.name}-public-*"]
  }
}

# A subzona que a raiz `dns/` criou e delegou. Lida por nome, não por id: o id muda se a
# zona for recriada, o nome não.
data "aws_route53_zone" "subzone" {
  name         = local.subzone_fqdn
  private_zone = false
}

# --------------------------------------------------------------------------------------
# Transit Gateway
# --------------------------------------------------------------------------------------

# O isolamento por tenant começa aqui, nos dois `disable`. O TGW nasce com association e
# propagation default LIGADOS: com eles, todo attachment aprende todo mundo e spoke fala com
# spoke sem ninguém ter pedido. Desligados, cada attachment só alcança o que uma route table
# explícita disser — spoke nasce isolada, e habilitar é aditivo e visível em diff.
resource "aws_ec2_transit_gateway" "hub" {
  description = "Hub de transito de us-east-1. Association e propagation default desligados de proposito."

  default_route_table_association = "disable"
  default_route_table_propagation = "disable"

  # DNS entre attachments; nao substitui resolucao de NOME entre VPCs, que e o 2.4.
  dns_support = "enable"

  tags = merge(local.tags, { Name = "${local.name}-tgw" })
}

# Route table do próprio hub. As de tenant (`tgw-rt-<spoke>`) NÃO nascem aqui: o ciclo de
# vida delas é o do spoke, então moram no state do spoke mesmo sendo recurso da conta
# network — é a fronteira de state por ciclo de vida, não por conta.
resource "aws_ec2_transit_gateway_route_table" "hub" {
  transit_gateway_id = aws_ec2_transit_gateway.hub.id

  tags = merge(local.tags, { Name = "${local.name}-tgw-rt-hub" })
}

# --------------------------------------------------------------------------------------
# RAM — pré-requisito de attachment cross-conta
# --------------------------------------------------------------------------------------

# O TGW pertence à conta network; a VPC de cada spoke pertence a outra conta. A AWS só permite
# `CreateTransitGatewayVpcAttachment` de outra conta depois de compartilhar o TGW via RAM.
resource "aws_ram_resource_share" "tgw" {
  name = "${local.name}-tgw"

  # allow_external_principals = false: o compartilhamento fica dentro desta Organization, não
  # com contas de fora. As spokes já estão todas na mesma Organization (Frente A).
  allow_external_principals = false

  tags = merge(local.tags, { Name = "${local.name}-tgw-share" })
}

resource "aws_ram_resource_association" "tgw" {
  resource_arn       = aws_ec2_transit_gateway.hub.arn
  resource_share_arn = aws_ram_resource_share.tgw.arn
}

# Uma por conta spoke — cresce quando uma spoke nova entra, ao contrário da rota abaixo.
resource "aws_ram_principal_association" "spoke" {
  for_each = toset(var.spoke_account_ids)

  principal          = each.value
  resource_share_arn = aws_ram_resource_share.tgw.arn
}

# --------------------------------------------------------------------------------------
# Attachment da própria VPC hub — sem ele, o que chega pelo túnel na subnet privada não tem
# como sair para o TGW.
# --------------------------------------------------------------------------------------

resource "aws_ec2_transit_gateway_vpc_attachment" "hub" {
  vpc_id     = data.aws_vpc.hub.id
  subnet_ids = data.aws_subnets.hub_private.ids

  transit_gateway_id = aws_ec2_transit_gateway.hub.id

  # Mesma disciplina do TGW em si: nada entra por default, associação e propagação são
  # explícitas abaixo.
  transit_gateway_default_route_table_association = false
  transit_gateway_default_route_table_propagation = false

  tags = merge(local.tags, { Name = "${local.name}-tgw-attachment" })
}

resource "aws_ec2_transit_gateway_route_table_association" "hub" {
  transit_gateway_attachment_id  = aws_ec2_transit_gateway_vpc_attachment.hub.id
  transit_gateway_route_table_id = aws_ec2_transit_gateway_route_table.hub.id
}

# A route table privada do hub já existe (network-foundation/, T0) — lida por tag, mesmo
# padrão da VPC e das subnets, não por terraform_remote_state.
data "aws_route_table" "hub_private" {
  filter {
    name   = "tag:Name"
    values = ["${local.name}-rt-private"]
  }
}

# Uma rota só, para a supernet inteira, para sempre: rota é TOPOLOGIA e não cresce por spoke —
# quem cresce por spoke é a authorization rule (política), não esta rota.
resource "aws_route" "hub_to_tgw" {
  route_table_id         = data.aws_route_table.hub_private.id
  destination_cidr_block = local.supernet
  transit_gateway_id     = aws_ec2_transit_gateway.hub.id

  depends_on = [aws_ec2_transit_gateway_vpc_attachment.hub]
}

# --------------------------------------------------------------------------------------
# Certificado do endpoint
# --------------------------------------------------------------------------------------

# Público do ACM, validado por DNS na subzona — não autoassinado importado. A escolha ficou
# possível quando o 1.3 entregou a subzona delegada, e o que ela compra é que NENHUMA chave
# privada existe em state nem em disco. A rotação é automática e o Client VPN a acompanha
# ("whether through ACM auto-rotation..." na doc de federated authentication).
#
# O certificado é recriado junto com esta camada toda noite, e isso não quebra o material de
# client: o que o .ovpn embute é a cadeia da CA pública da Amazon, que não muda entre
# emissões. Era esse o ponto de declarar o certificado T0 — e uma CA pública o entrega melhor
# que um autoassinado de vida longa.
resource "aws_acm_certificate" "vpn" {
  domain_name       = local.vpn_fqdn
  validation_method = "DNS"

  tags = merge(local.tags, { Name = local.vpn_fqdn })

  lifecycle {
    create_before_destroy = true
  }
}

# UM registro, indexado — não `for_each` sobre `domain_validation_options` como no exemplo
# oficial. O for_each daquele exemplo exige que as CHAVES do mapa sejam conhecidas no plan, e
# elas vêm de atributo computado; com um domínio só e nenhum SAN, o conjunto tem exatamente um
# elemento e indexar é determinístico. Se um dia entrar SAN aqui, isto tem de virar for_each
# sobre uma lista de domínios vinda da CONFIGURAÇÃO, não do atributo.
resource "aws_route53_record" "vpn_validation" {
  zone_id = data.aws_route53_zone.subzone.zone_id
  name    = tolist(aws_acm_certificate.vpn.domain_validation_options)[0].resource_record_name
  type    = tolist(aws_acm_certificate.vpn.domain_validation_options)[0].resource_record_type
  records = [tolist(aws_acm_certificate.vpn.domain_validation_options)[0].resource_record_value]

  # TTL curto pelo mesmo motivo do NS da pai: a subzona é recriada com esta camada, e uma
  # validação pendente presa por cache seria tempo perdido em cada apply da manhã.
  ttl = 60

  # O registro de validação é efêmero por natureza — sobrescrever é o comportamento certo.
  allow_overwrite = true
}

# Sem isto o endpoint pode ser criado apontando para um certificado ainda PENDING_VALIDATION,
# e a falha aparece na conexão, não no apply.
resource "aws_acm_certificate_validation" "vpn" {
  certificate_arn         = aws_acm_certificate.vpn.arn
  validation_record_fqdns = [aws_route53_record.vpn_validation.fqdn]
}

# --------------------------------------------------------------------------------------
# Client VPN
# --------------------------------------------------------------------------------------

# O provider SAML é o que liga o endpoint ao Identity Center. O metadata NÃO é gerado por
# Terraform: a API `CreateApplication` do Identity Center só cria aplicações OAuth 2.0
# customizadas, então a aplicação SAML é passo de console e o XML dela entra por arquivo.
resource "aws_iam_saml_provider" "client_vpn" {
  name                   = "${local.name}-client-vpn"
  saml_metadata_document = file(var.saml_metadata_path)

  tags = merge(local.tags, { Name = "${local.name}-client-vpn" })
}

resource "aws_ec2_client_vpn_endpoint" "hub" {
  description = "Acesso de manutencao a rede privada, autenticado pelo Identity Center."

  server_certificate_arn = aws_acm_certificate_validation.vpn.certificate_arn
  client_cidr_block      = var.client_cidr_block

  # split_tunnel: só o que a route table do endpoint listar entra no túnel. Sem isso todo o
  # tráfego da máquina do operador passaria pela AWS — custo de dados e um caminho de saída
  # que ninguém pediu.
  split_tunnel = true

  # A VPC do endpoint é a hub. NÃO se usa `transit_gateway_configuration`, que existe e
  # pareceria mais direto: o attachment que aquele bloco cria leva HORAS para ser deletado e
  # impede a deleção do TGW (aviso na doc do provider) — incompatível com destruir esta
  # camada toda noite. E o 2.4 depende de as ENIs do endpoint viverem na VPC hub, para o
  # resolver da VPC ser local a elas.
  vpc_id = data.aws_vpc.hub.id

  authentication_options {
    type              = "federated-authentication"
    saml_provider_arn = aws_iam_saml_provider.client_vpn.arn
  }

  # Desligado: logging por conexão exige log group, que é custo e retenção a decidir. O que
  # se perde é a trilha de quem conectou quando — item de hardening, não de operabilidade.
  connection_log_options {
    enabled = false
  }

  tags = merge(local.tags, { Name = "${local.name}-client-vpn" })
}

# É a associação que tira o endpoint de `pending-associate` e o torna conectável. Uma por AZ,
# em subnet PRIVADA: os requisitos de target network não pedem rota para o IGW (isso é
# prerequisito do tutorial de mutual auth, onde o túnel É o caminho de internet). Aqui o
# tráfego que importa vai para o supernet, pelo TGW.
resource "aws_ec2_client_vpn_network_association" "hub" {
  for_each = toset(data.aws_subnets.hub_private.ids)

  client_vpn_endpoint_id = aws_ec2_client_vpn_endpoint.hub.id
  subnet_id              = each.value
}

# Uma rota, o supernet inteiro. A local da VPC hub (10.1.0.0/16) a AWS acrescenta sozinha na
# associação — as duas convivem por prefixo mais longo.
resource "aws_ec2_client_vpn_route" "supernet" {
  for_each = toset(data.aws_subnets.hub_private.ids)

  client_vpn_endpoint_id = aws_ec2_client_vpn_endpoint.hub.id
  destination_cidr_block = local.supernet
  target_vpc_subnet_id   = each.value

  # A rota depende da associação da MESMA subnet: criar antes falha com "subnet não
  # associada", e o for_each sozinho não garante ordem.
  depends_on = [aws_ec2_client_vpn_network_association.hub]
}

# A política de quem alcança o quê. Uma rule por grupo, e `access_group_id` é metade do valor
# de ter escolhido SAML — é o que permite "o Fulano só chega na spoke dele".
#
# `authorize_all_groups` NUNCA entra aqui: com ele, todo mundo que autentica alcança o CIDR e
# a distinção por grupo desaparece — sem erro, sem aviso.
resource "aws_ec2_client_vpn_authorization_rule" "operators" {
  for_each = var.manage_authorization ? toset(var.operator_group_ids) : toset([])

  client_vpn_endpoint_id = aws_ec2_client_vpn_endpoint.hub.id
  target_network_cidr    = local.supernet
  access_group_id        = each.value
}

# --------------------------------------------------------------------------------------
# Ingress do hub — ALB público (3.2)
# --------------------------------------------------------------------------------------

# Por que o ALB vive NESTA camada e não na network-foundation (T0, permanente): sem TGW ele
# não alcança spoke nenhuma — é um listener servindo 404. O ciclo de vida dele é o do plano
# de conectividade, e um hub novo (outra região) ganha o seu com a própria raiz
# connectivity/<região>/.
#
# Consequência aceita e declarada: o teardown noturno desta camada leva o ingress público de
# TODAS as células junto. O horizonte é ingress por célula, para o ALB do hub deixar de ser
# ponto único de falha — quando isso existir, ele passa a ser um caminho entre vários, o que
# reforça mantê-lo em camada descartável.
resource "aws_security_group" "alb" {
  name        = "${local.name}-ingress-alb"
  description = "Public ingress ALB: accepts HTTPS from the internet, reaches spokes only"
  vpc_id      = data.aws_vpc.hub.id

  tags = merge(local.tags, { Name = "${local.name}-ingress-alb" })

  lifecycle {
    create_before_destroy = true
  }
}

# 0.0.0.0/0 na ENTRADA é o valor certo aqui, e é o oposto do NLB da spoke, onde a mesma
# constante é proibida por decisão. Este é o ponto de entrada público único do desenho.
resource "aws_vpc_security_group_ingress_rule" "alb_https" {
  security_group_id = aws_security_group.alb.id
  description       = "Public HTTPS"

  cidr_ipv4   = "0.0.0.0/0"
  ip_protocol = "tcp"
  from_port   = 443
  to_port     = 443
}

# O listener :80 só redireciona, mas sem esta regra o redirect é inalcançável e o sintoma
# ("http não responde") parece problema de DNS.
resource "aws_vpc_security_group_ingress_rule" "alb_http_redirect" {
  security_group_id = aws_security_group.alb.id
  description       = "Public HTTP, redirected to HTTPS"

  cidr_ipv4   = "0.0.0.0/0"
  ip_protocol = "tcp"
  from_port   = 80
  to_port     = 80
}

# A SAÍDA é o que contém o blast radius: o supernet cobre qualquer spoke presente ou futura
# pelo TGW, e nada além. 0.0.0.0/0 aqui transformaria o ALB num caminho de saída para a
# internet. Porta 80 porque o trecho hub→spoke é HTTP puro de propósito — o ALB não valida
# certificado de backend, então TLS ali custaria gerência sem ganhar verificação.
resource "aws_vpc_security_group_egress_rule" "alb_to_spokes" {
  security_group_id = aws_security_group.alb.id
  description       = "Reach the internal ingress NLB of any spoke"

  cidr_ipv4   = local.supernet
  ip_protocol = "tcp"
  from_port   = 80
  to_port     = 80
}

resource "aws_lb" "hub" {
  name               = "${local.name}-ingress"
  load_balancer_type = "application"
  internal           = false
  ip_address_type    = "ipv4"
  security_groups    = [aws_security_group.alb.id]

  # As PÚBLICAS. Um internet-facing em subnet privada não tem rota para o IGW e falha em
  # silêncio: o ALB é criado, fica `active`, e nada da internet chega.
  subnets = data.aws_subnets.hub_public.ids

  tags = merge(local.tags, { Name = "${local.name}-ingress" })
}

# Certificado default do listener. Mesmo padrão do certificado do Client VPN acima: público
# do ACM, validado por DNS na subzona que já é nossa, nenhuma chave privada em state ou disco.
resource "aws_acm_certificate" "alb" {
  domain_name       = local.alb_default_fqdn
  validation_method = "DNS"

  tags = merge(local.tags, { Name = local.alb_default_fqdn })

  lifecycle {
    create_before_destroy = true
  }
}

# UM registro, indexado — mesma razão detalhada no vpn_validation acima: as chaves de um
# for_each sobre domain_validation_options viriam de atributo computado. Um domínio, nenhum
# SAN, um elemento.
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

# O listener compartilhado. Um só, por SNI: cada célula anexa o próprio certificado por
# aws_lb_listener_certificate a partir do state dela, e casa o próprio host por listener rule.
#
# O certificate_arn vem do VALIDATION, não do certificate: só ele espera a validação
# terminar. Os dois ARNs são o mesmo valor, então nenhum teste offline distingue as duas
# referências — o sintoma de errar é certificado PENDING_VALIDATION no listener.
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.hub.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate_validation.alb.certificate_arn

  # Host que não casa nenhuma rule recebe 404 explícito. O default do ALB seria erro de
  # configuração, e um 503 não distinguiria "host desconhecido" de "backend caído".
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
