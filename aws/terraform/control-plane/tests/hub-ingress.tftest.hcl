# 3.2 — o lado HUB do ingress desta célula, na conta network via provider aliasado.
#
# Fronteira de state segue o ciclo de vida, não a conta: certificado, target group, listener
# rule e registro DNS são da célula, então moram no state dela mesmo sendo recursos da conta
# network. Destruir a célula leva os quatro junto, sem órfão do lado do hub.
#
# O ALB e o listener :443 NÃO nascem aqui — são permanentes, da camada 03, e vêm por data
# source. Um listener por hub, N certificados por SNI, uma rule por célula.

mock_provider "aws" {}

mock_provider "aws" {
  alias = "network"
}

mock_provider "kubernetes" {}
mock_provider "helm" {}

variables {
  name                = "control-plane"
  region              = "us-east-1"
  aws_profile         = "cicd"
  network_profile     = "network"
  hub_vpc_name        = "poc-hub-vpc"
  vpc_cidr            = "10.2.0.0/16"
  availability_zones  = ["us-east-1a", "us-east-1b"]
  target_account_ids  = ["000000000000"]
  network_account_id  = "111111111111"
  public_access_cidrs = ["203.0.113.10/32"]
  base_domain         = "exemplo.com"
}

override_data {
  target = data.aws_vpc.hub
  values = {
    id         = "vpc-hub000000000001"
    cidr_block = "10.1.0.0/16"
  }
}

override_data {
  target = data.aws_route53_zone.subzone
  values = {
    zone_id = "ZSUBZONE00000000001"
  }
}

override_data {
  target = data.aws_lb.hub_ingress
  values = {
    arn     = "arn:aws:elasticloadbalancing:us-east-1:111111111111:loadbalancer/app/poc-hub-ingress/0000000000000001"
    dns_name = "poc-hub-ingress-000000001.us-east-1.elb.amazonaws.com"
    zone_id  = "Z35SXDOTRQ7X7K"
  }
}

override_data {
  target = data.aws_lb_listener.hub_https
  values = {
    arn = "arn:aws:elasticloadbalancing:us-east-1:111111111111:listener/app/poc-hub-ingress/0000000000000001/aaaaaaaaaaaaaaaa"
  }
}

# --------------------------------------------------------------------------------------
# Certificado da célula
# --------------------------------------------------------------------------------------

run "o_certificado_da_celula_e_wildcard_de_um_nivel_sob_a_subzona" {
  command = plan

  # Wildcard cobre UM nível: *.control-plane.nonprod.exemplo.com casa
  # app.control-plane.nonprod.exemplo.com. `*.*.` não existe, e é por isso que há um
  # certificado por célula em vez de um só na subzona.
  assert {
    condition     = aws_acm_certificate.cell.domain_name == "*.control-plane.nonprod.exemplo.com"
    error_message = "esperado *.control-plane.nonprod.exemplo.com, veio ${aws_acm_certificate.cell.domain_name}"
  }

  assert {
    condition     = aws_acm_certificate.cell.validation_method == "DNS"
    error_message = "validação por DNS: a subzona é nossa e não há chave privada em state"
  }

  # O ACM é mais restrito que a tag comum de EC2: valor de tag tem de casar
  # `([\p{L}\p{Z}\p{N}_.:/=+\-@]*)`, e `*` está FORA. Copiar o domain_name para a tag Name
  # derrubou o primeiro apply do 3.2 com ValidationException apontando `tags.1.member.value` —
  # índice, não nome de tag. Mesma guarda existe na camada 03.
  assert {
    condition = alltrue([
      for value in values(aws_acm_certificate.cell.tags) :
      can(regex("^[[:alnum:]_.:/=+@ -]*$", value))
    ])
    error_message = "valor de tag do ACM fora do padrão aceito pelo serviço (provavelmente um `*` de wildcard)"
  }

  assert {
    condition     = aws_route53_record.cell_validation.zone_id == "ZSUBZONE00000000001"
    error_message = "a validação vai para a SUBZONA (autoritativa pelo nome da célula), não para a pai"
  }
}

# --------------------------------------------------------------------------------------
# Target group do hub
# --------------------------------------------------------------------------------------

run "a_target_group_do_hub_aponta_para_os_enderecos_fixos_do_nlb" {
  command = plan

  # Estes endereços vêm de var.vpc_cidr, atravessam o módulo network e voltam pelo módulo
  # ingress. Foi para isso que foram FIXADOS: são conhecidos em tempo de plan, então o lado
  # hub pode ser planejado sem o NLB existir.
  assert {
    condition = toset([for a in aws_lb_target_group_attachment.hub_to_cell : a.target_id]) == toset(["10.2.32.10", "10.2.48.10"])
    error_message = "a target group do hub deveria registrar os IPs fixos do NLB, recebido ${jsonencode([for a in aws_lb_target_group_attachment.hub_to_cell : a.target_id])}"
  }

  # IP fora da VPC do load balancer exige availability_zone = "all". Omitir dá erro que não
  # explica a causa — o NLB está na VPC da SPOKE, o ALB na VPC hub.
  assert {
    condition     = alltrue([for a in aws_lb_target_group_attachment.hub_to_cell : a.availability_zone == "all"])
    error_message = "IP fora da VPC do load balancer exige availability_zone = all"
  }

  # A target group vive na VPC HUB (é lá que está o ALB), não na VPC da spoke.
  assert {
    condition     = aws_lb_target_group.hub_to_cell.vpc_id == "vpc-hub000000000001"
    error_message = "a target group do hub pertence à VPC hub, veio ${aws_lb_target_group.hub_to_cell.vpc_id}"
  }

  # HTTP puro no trecho hub→spoke, de propósito: o ALB não valida certificado de backend,
  # então TLS ali custaria gerência sem ganhar verificação.
  assert {
    condition     = aws_lb_target_group.hub_to_cell.protocol == "HTTP" && aws_lb_target_group.hub_to_cell.port == 80
    error_message = "o trecho hub→spoke é HTTP na 80"
  }

  # name_prefix, nunca name: trocar porta ou target_type força replace, e com nome fixo não há
  # saída (sem CBD a AWS recusa apagar, com CBD recusa criar a nova). Preço: 6 caracteres.
  assert {
    condition     = aws_lb_target_group.hub_to_cell.name_prefix != null && aws_lb_target_group.hub_to_cell.name_prefix != ""
    error_message = "a target group tem de usar name_prefix"
  }
}

run "o_health_check_aceita_404_porque_o_envoy_responde_404_ao_host_do_ip" {
  command = plan

  # A armadilha central do 3.2. O health check chega ao Envoy com Host = IP do nó do ALB, que
  # não casa nenhum VirtualService, e o Istio responde 404. Com o matcher default (200) TODOS
  # os targets ficam unhealthy sem nada estar errado.
  #
  # 200-404 é escolha CONSCIENTE e provisória: ela aceita como saudável um gateway realmente
  # quebrado, porque 404 é exatamente o que um Envoy sem configuração devolve. Estreitar para
  # 200 depende de uma rota de health no Gateway/VirtualService casando qualquer host — que é
  # manifesto de GitOps, não Terraform. Não existe porta de status alcançável daqui: a 15021 é
  # do gateway DENTRO da spoke, e o listener do NLB só escuta 80.
  assert {
    condition     = one(aws_lb_target_group.hub_to_cell.health_check).matcher == "200-404"
    error_message = "matcher tem de aceitar 404 enquanto não houver rota de health, veio ${one(aws_lb_target_group.hub_to_cell.health_check).matcher}"
  }
}

# Segundo run com OUTRO CIDR de spoke. Sem ele, uma lista de IPs cravada à mão no main.tf
# igual à esperada passa verde — comprovado por mutação: `for_each = toset(["10.2.32.10",
# "10.2.48.10"])` sobrevivia ao run acima. Aqui os endereços têm de acompanhar var.vpc_cidr
# através do módulo network e do módulo ingress, e nenhuma lista fixa satisfaz os dois runs.
run "os_alvos_acompanham_o_cidr_da_spoke" {
  command = plan

  variables {
    name     = "control-plane"
    vpc_cidr = "10.5.0.0/16"
  }

  assert {
    condition = toset([for a in aws_lb_target_group_attachment.hub_to_cell : a.target_id]) == toset(["10.5.32.10", "10.5.48.10"])
    error_message = "os alvos deveriam derivar de vpc_cidr, recebido ${jsonencode([for a in aws_lb_target_group_attachment.hub_to_cell : a.target_id])}"
  }
}

# --------------------------------------------------------------------------------------
# Listener rule e DNS
# --------------------------------------------------------------------------------------

run "a_rule_casa_o_host_da_celula_e_encaminha_para_a_target_group_dela" {
  command = plan

  assert {
    condition = one(one(aws_lb_listener_rule.cell.condition).host_header).values == toset(["*.control-plane.nonprod.exemplo.com"])
    error_message = "a rule tem de casar o wildcard da célula"
  }

  # Priority único por listener, derivado de algo estável da célula — não de count.index, que
  # mudaria se a ordem mudasse. Faixa válida do ALB: 1..50000.
  assert {
    condition     = aws_lb_listener_rule.cell.priority >= 1 && aws_lb_listener_rule.cell.priority <= 50000
    error_message = "priority fora da faixa do ALB: ${aws_lb_listener_rule.cell.priority}"
  }
}

run "o_registro_da_celula_e_alias_wildcard_para_o_alb_do_hub" {
  command = plan

  assert {
    condition     = aws_route53_record.cell_wildcard.name == "*.control-plane"
    error_message = "o registro é o wildcard da célula dentro da subzona, veio ${aws_route53_record.cell_wildcard.name}"
  }

  assert {
    condition     = aws_route53_record.cell_wildcard.type == "A"
    error_message = "alias de ALB é registro A, não CNAME"
  }

  # dns_name e zone_id têm de vir do MESMO data source do ALB. Um alias com zone_id de outro
  # load balancer é aceito pelo Route53 e nunca resolve.
  assert {
    condition = one(aws_route53_record.cell_wildcard.alias).zone_id == "Z35SXDOTRQ7X7K"
    error_message = "o alias tem de usar a zone_id canônica do ALB do hub"
  }
}

# --------------------------------------------------------------------------------------
# O que NÃO está coberto, e por quê
# --------------------------------------------------------------------------------------

# A ORDENAÇÃO entre validação e uso do certificado não é assertável offline, nos DOIS lugares
# onde importa: aws_lb_listener_certificate tem de referenciar
# aws_acm_certificate_validation.cell.certificate_arn, não aws_acm_certificate.cell.arn. Os
# dois ARNs são o MESMO valor, então nenhuma asserção distingue as referências e a mutação
# passa verde (armadilha catalogada em aws/terraform/CLAUDE.md). O sintoma real é certificado
# PENDING_VALIDATION anexado ao listener, e só um apply o pega.
