# 3.2 — o lado hub do ingress: ALB público, listener :443 compartilhado por SNI e o
# certificado default da subzona.
#
# Por que o ALB vive nesta camada e não na network-foundation (T0): sem TGW ele não alcança
# spoke nenhuma — é um listener servindo 404. O ciclo de vida dele é o do plano de
# conectividade. Consequência aceita: o teardown noturno leva o ingress público junto.

mock_provider "aws" {}

variables {
  base_domain        = "exemplo.com"
  operator_group_ids = ["11111111-2222-3333-4444-555555555555"]
  region             = "us-east-1"
  vpc_cidr           = "10.1.0.0/16"
  availability_zones = ["a", "b"]
  saml_metadata_path = "tests/fixtures/saml-metadata.xml"
  spoke_account_ids  = ["222222222222"]
}

# Os data sources que a connectivity/ usava para achar a VPC hub e suas subnets por tag
# morreram: dentro do modulo a VPC e do proprio grafo, e module.network expoe tudo como output.
# O que era override_data de descoberta agora e override_module do submodulo.
override_module {
  target = module.network

  outputs = {
    vpc_id                 = "vpc-hub000000000001"
  vpc_cidr               = "10.1.0.0/16"
  private_subnet_ids     = ["subnet-priv0000000a", "subnet-priv0000000b"]
  public_subnet_ids      = ["subnet-pub00000000a", "subnet-pub00000000b"]
  private_route_table_id = "rtb-hubprivate00001"
    public_route_table_id  = "rtb-hubpublic000001"
  }
}

override_data {
  target = data.aws_route53_zone.subzone
  values = {
    zone_id = "ZSUBZONE00000000001"
  }
}

# Mesma razão do override global em spoke-attachment.tftest.hcl: sem um arn válido,
# aws_ram_resource_association falha na validação de schema do provider (client-side, sob
# mock) por um motivo que nada tem a ver com o que cada run pretende testar.
override_resource {
  target = aws_ec2_transit_gateway.hub
  values = {
    arn = "arn:aws:ec2:us-east-1:000000000000:transit-gateway/tgw-0000000000000000f"
  }
}

# --------------------------------------------------------------------------------------
# Certificado default do listener
# --------------------------------------------------------------------------------------

run "certificado_default_e_o_wildcard_da_subzona" {
  command = plan

  # Wildcard cobre UM nível só: *.us-east-1.nonprod.exemplo.com casa app.us-east-1.nonprod.exemplo.com,
  # e NÃO casa app.<id>.nonprod.exemplo.com. É por isso que ele serve de certificado DEFAULT do
  # listener, e os certificados por célula entram por SNI a partir do state da célula. A região
  # entra no nome pelo mesmo motivo do FQDN da VPN: sem ela, dois hubs disputam o mesmo record de
  # validação DNS-01 (regional-naming.tftest.hcl cobre a prova de mutação com duas regiões).
  assert {
    condition     = aws_acm_certificate.alb.domain_name == "*.us-east-1.nonprod.exemplo.com"
    error_message = "esperado *.us-east-1.nonprod.exemplo.com, veio ${aws_acm_certificate.alb.domain_name}"
  }

  assert {
    condition     = aws_acm_certificate.alb.validation_method == "DNS"
    error_message = "validação tem de ser DNS: a zona é nossa e não há chave privada em state"
  }

  # O ACM é mais restrito que a tag comum de EC2: valor de tag tem de casar
  # `([\p{L}\p{Z}\p{N}_.:/=+\-@]*)`, e `*` está FORA. Copiar o domain_name para a tag Name
  # (o que era natural, e é o que os outros recursos daqui fazem) derrubou um apply real com
  # ValidationException apontando `tags.2.member.value` — índice, não nome de tag.
  assert {
    condition = alltrue([
      for value in values(aws_acm_certificate.alb.tags) :
      can(regex("^[[:alnum:]_.:/=+@ -]*$", value))
    ])
    error_message = "valor de tag do ACM fora do padrão aceito pelo serviço (provavelmente um `*` de wildcard)"
  }

  assert {
    condition     = aws_route53_record.alb_validation.zone_id == "ZSUBZONE00000000001"
    error_message = "o registro de validação tem de ir para a subzona, não para a pai"
  }

  # O registro é efêmero e a camada é recriada toda noite — sem allow_overwrite o apply da
  # manhã falha porque o registro da noite anterior ainda está lá.
  assert {
    condition     = aws_route53_record.alb_validation.allow_overwrite == true
    error_message = "o registro de validação precisa de allow_overwrite"
  }
}

# --------------------------------------------------------------------------------------
# Security group
# --------------------------------------------------------------------------------------

run "o_alb_aceita_a_internet_e_so_alcanca_o_supernet" {
  command = plan

  # Aqui 0.0.0.0/0 na ENTRADA é o valor certo — este é o ponto de entrada público. É o
  # oposto do NLB da spoke, onde a mesma constante é proibida por decisão (ingress único
  # pelo hub).
  assert {
    condition     = aws_vpc_security_group_ingress_rule.alb_https.cidr_ipv4 == "0.0.0.0/0"
    error_message = "o ALB é público na porta 443: esperado 0.0.0.0/0, veio ${aws_vpc_security_group_ingress_rule.alb_https.cidr_ipv4}"
  }

  assert {
    condition     = aws_vpc_security_group_ingress_rule.alb_https.from_port == 443
    error_message = "a entrada pública é 443"
  }

  # O listener :80 só redireciona, mas sem esta regra o redirect nunca é alcançado e o
  # sintoma é "http não responde" parecendo problema de DNS.
  assert {
    condition     = aws_vpc_security_group_ingress_rule.alb_http_redirect.from_port == 80
    error_message = "sem entrada em 80 o listener de redirect é inalcançável"
  }

  # A SAÍDA é o que contém o blast radius: o ALB alcança o supernet (qualquer spoke,
  # presente ou futura, pelo TGW) e nada além. 0.0.0.0/0 aqui transformaria o ALB em
  # caminho de saída para a internet.
  assert {
    condition     = aws_vpc_security_group_egress_rule.alb_to_spokes.cidr_ipv4 == "10.0.0.0/12"
    error_message = "a saída do ALB é o supernet, não ${aws_vpc_security_group_egress_rule.alb_to_spokes.cidr_ipv4}"
  }

  assert {
    condition     = aws_vpc_security_group_egress_rule.alb_to_spokes.from_port == 80
    error_message = "o trecho hub→spoke é HTTP puro de propósito: o ALB não valida certificado de backend"
  }
}

# --------------------------------------------------------------------------------------
# O ALB
# --------------------------------------------------------------------------------------

run "o_alb_e_publico_e_nasce_nas_subnets_publicas" {
  command = plan

  assert {
    condition     = aws_lb.hub.internal == false
    error_message = "o ALB do hub é o ponto de entrada público"
  }

  assert {
    condition     = aws_lb.hub.load_balancer_type == "application"
    error_message = "tem de ser ALB: o roteamento por host_header não existe em NLB"
  }

  # A asserção que importa: internet-facing em subnet PRIVADA não tem rota para o IGW e
  # falha em silêncio — o ALB é criado, fica `active`, e nada da internet chega.
  assert {
    condition     = toset(aws_lb.hub.subnets) == toset(["subnet-pub00000000a", "subnet-pub00000000b"])
    error_message = "o ALB não nasceu nas públicas: ${jsonencode(aws_lb.hub.subnets)}"
  }

  # Pega a troca mais provável: as privadas também são duas, então nenhuma asserção de
  # tamanho distinguiria uma da outra.
  assert {
    condition     = length(setintersection(toset(aws_lb.hub.subnets), toset(["subnet-priv0000000a", "subnet-priv0000000b"]))) == 0
    error_message = "o ALB está numa subnet privada"
  }
}

# Segundo run com tamanho diferente: UM override_data prova o valor, não a ligação — uma
# lista de ids colada à mão no main.tf igual à injetada acima passaria verde. Nenhuma lista
# fixa satisfaz dois tamanhos.
run "as_subnets_do_alb_acompanham_a_descoberta" {
  command = plan

  override_module {
    target = module.network

    outputs = {
      vpc_id                 = "vpc-hub000000000001"
      vpc_cidr               = "10.1.0.0/16"
      private_subnet_ids     = ["subnet-priv0000000a", "subnet-priv0000000b"]
      public_subnet_ids      = ["subnet-pub00000002a", "subnet-pub00000002b", "subnet-pub00000002c"]
      private_route_table_id = "rtb-hubprivate00001"
      public_route_table_id  = "rtb-hubpublic000001"
    }
  }

  assert {
    condition     = toset(aws_lb.hub.subnets) == toset(["subnet-pub00000002a", "subnet-pub00000002b", "subnet-pub00000002c"])
    error_message = "as subnets do ALB não vieram do data source: ${jsonencode(aws_lb.hub.subnets)}"
  }
}

# --------------------------------------------------------------------------------------
# Listeners
# --------------------------------------------------------------------------------------

run "o_listener_443_responde_404_sem_rule_casando" {
  command = plan

  assert {
    condition     = aws_lb_listener.https.port == 443
    error_message = "o listener público é 443"
  }

  assert {
    condition     = aws_lb_listener.https.protocol == "HTTPS"
    error_message = "protocolo HTTPS: é onde o TLS do usuário termina"
  }

  # Sem rule casando, 404 explícito. O default do ALB seria erro de configuração, e um 503
  # aqui não distinguiria "host desconhecido" de "backend caído".
  assert {
    condition     = one(aws_lb_listener.https.default_action).type == "fixed-response"
    error_message = "o default_action tem de ser fixed-response"
  }

  assert {
    condition     = one(one(aws_lb_listener.https.default_action).fixed_response).status_code == "404"
    error_message = "host que não casa nenhuma rule é 404, não 503"
  }
}

run "o_listener_80_redireciona_para_443" {
  command = plan

  assert {
    condition     = aws_lb_listener.http_redirect.port == 80
    error_message = "o listener de redirect é 80"
  }

  assert {
    condition     = one(aws_lb_listener.http_redirect.default_action).type == "redirect"
    error_message = "o listener 80 só redireciona — nada é servido em claro"
  }

  assert {
    condition     = one(one(aws_lb_listener.http_redirect.default_action).redirect).status_code == "HTTP_301"
    error_message = "redirect permanente: o host canônico é https"
  }

  assert {
    condition     = one(one(aws_lb_listener.http_redirect.default_action).redirect).port == "443"
    error_message = "o redirect aponta para 443"
  }
}

# --------------------------------------------------------------------------------------
# O que NÃO está coberto, e por quê
# --------------------------------------------------------------------------------------

# A ORDENAÇÃO entre o certificado e o listener não é assertável aqui. O listener tem de
# referenciar aws_acm_certificate_validation.alb.certificate_arn, não
# aws_acm_certificate.alb.arn: só o primeiro espera a validação. Os dois ARNs são o MESMO
# valor, então nenhuma asserção de valor distingue as duas referências e a mutação passa
# verde (armadilha catalogada em aws/terraform/CLAUDE.md, mesma família de
# aws_acm_certificate_validation.vpn). O sintoma real é certificado PENDING_VALIDATION no
# listener, e só um apply o pega. Escrito aqui em vez de coberto por uma asserção que
# passaria de qualquer jeito.
