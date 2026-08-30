# 3.1 — a parte do ingress que só existe na composição.
#
# src/ingress/tests/ já prova o módulo isolado (endereço fixo por subnet, target group de tipo
# ip, health check na porta de status, SG fechado no hub). O que sobra para cá é a FIAÇÃO: que
# os CIDRs das subnets da spoke chegam ao subnet_mapping do NLB, e que o SG do cluster abre as
# portas do gateway para o SG do NLB — dois módulos que só se conhecem aqui.

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
  vpc_cidr            = "10.2.0.0/16"
  target_account_ids  = ["000000000000"]
  network_account_id  = "111111111111"
  public_access_cidrs = ["203.0.113.10/32"]

  # 3.2 tornou base_domain obrigatoria (sem default, falha-fechado). Ela nao tem
  # relacao com o que este arquivo testa — sem o valor, nenhum run deste arquivo executa.
  base_domain = "exemplo.com"

  # O hub, por referencia — ver o comentario no variables.tf do modulo. hub_vpc_cidr_block tem
  # um segundo papel aqui: e o CIDR hub que vira allowed_ingress_cidrs do NLB.
  hub_vpc_id                         = "vpc-hub000000000001"
  hub_vpc_cidr_block                 = "10.1.0.0/16"
  transit_gateway_id                 = "tgw-00000000000000001"
  hub_transit_gateway_route_table_id = "tgw-rtb-00000000000000001"
  hub_transit_gateway_attachment_id  = "tgw-attach-00000000000000001"
  hub_alb_listener_arn               = "arn:aws:elasticloadbalancing:us-east-1:111111111111:listener/app/poc-hub-ingress/0000000000000001/aaaaaaaaaaaaaaaa"
  hub_alb_dns_name                   = "poc-hub-ingress-000000001.us-east-1.elb.amazonaws.com"
  hub_alb_zone_id                    = "Z35SXDOTRQ7X7K"
}

override_data {
  target = data.aws_availability_zones.this
  values = {
    names = ["us-east-1a", "us-east-1b"]
  }
}

# O endereço do NLB nasce de var.vpc_cidr, atravessa o módulo network (que fatia as subnets) e
# volta ao módulo ingress como private_subnet_cidrs. Nenhum apply é necessário: cidrsubnet e
# cidrhost são resolvidos no plan, então uma constante cravada em qualquer ponto do caminho
# aparece aqui como endereço errado.
run "os_enderecos_do_nlb_saem_das_subnets_da_spoke" {
  command = plan

  # /16 fatiado pelo módulo network: privadas em 10.2.32.0/20 e 10.2.48.0/20; host 10 de cada.
  assert {
    condition     = toset(module.ingress.private_ips) == toset(["10.2.32.10", "10.2.48.10"])
    error_message = "os IPs fixos do NLB deveriam sair das privadas da spoke, recebido ${jsonencode(module.ingress.private_ips)}"
  }

  # Um endereço por AZ — é isso que a target group do hub (3.2) vai apontar.
  assert {
    condition     = length(module.ingress.private_ips) == length(module.network.availability_zones)
    error_message = "um endereco por AZ, recebido ${length(module.ingress.private_ips)} para ${length(module.network.availability_zones)} AZs"
  }
}

# Segundo run com outro supernet: um só prova o valor, dois provam a ligação. Com este ausente,
# um `["10.2.32.10", "10.2.48.10"]` hardcoded no módulo passaria verde.
run "e_acompanha_a_spoke_em_outro_cidr" {
  command = plan

  variables {
    vpc_cidr = "10.7.0.0/16"
  }

  assert {
    condition     = toset(module.ingress.private_ips) == toset(["10.7.32.10", "10.7.48.10"])
    error_message = "trocando o CIDR da spoke os enderecos deveriam acompanhar, recebido ${jsonencode(module.ingress.private_ips)}"
  }
}

# As duas regras que o módulo ingress NÃO pode declarar: o SG de destino é o do cluster, que
# vive no outro módulo. Sem elas o NLB tem egress e o pod nunca recebe — sintoma "nenhum target
# saudável", longe da causa.
run "o_sg_do_cluster_abre_as_portas_do_gateway_para_o_nlb" {
  command = plan

  assert {
    condition     = aws_vpc_security_group_ingress_rule.gateway_from_nlb.from_port == 80 && aws_vpc_security_group_ingress_rule.gateway_from_nlb.to_port == 80
    error_message = "a porta do trafego e a do pod do gateway, recebido ${aws_vpc_security_group_ingress_rule.gateway_from_nlb.from_port}-${aws_vpc_security_group_ingress_rule.gateway_from_nlb.to_port}"
  }

  assert {
    condition     = aws_vpc_security_group_ingress_rule.gateway_health_check_from_nlb.from_port == 15021 && aws_vpc_security_group_ingress_rule.gateway_health_check_from_nlb.to_port == 15021
    error_message = "a porta do health check e a de status do Istio, recebido ${aws_vpc_security_group_ingress_rule.gateway_health_check_from_nlb.from_port}-${aws_vpc_security_group_ingress_rule.gateway_health_check_from_nlb.to_port}"
  }

  # Trafego e health check em portas DISTINTAS: iguais, as duas asserções acima passariam por
  # coincidência e o par de regras deixaria de distinguir os dois papéis.
  assert {
    condition     = aws_vpc_security_group_ingress_rule.gateway_from_nlb.from_port != aws_vpc_security_group_ingress_rule.gateway_health_check_from_nlb.from_port
    error_message = "trafego e health check tem de usar portas distintas"
  }

  assert {
    condition     = aws_vpc_security_group_ingress_rule.gateway_from_nlb.ip_protocol == "tcp" && aws_vpc_security_group_ingress_rule.gateway_health_check_from_nlb.ip_protocol == "tcp"
    error_message = "as duas regras sao TCP"
  }

  # Não há asserção sobre EM QUE security group as regras entram nem QUAL SG elas referenciam,
  # pela mesma razão registrada no private-access.tftest.hcl: `cluster_security_group_id` é
  # computado pelo EKS e `module.ingress.security_group_id` é computado pelo EC2 — os dois
  # lados de cada comparação seriam unknown, e `terraform test` recusa condição sobre unknown.
  #
  # O que sustenta a ligação sem teste: as regras usam `referenced_security_group_id`, não
  # CIDR, então não há valor literal que possa estar errado — só o nome da referência, que o
  # `terraform validate` já resolve.
}

# O contrato com o GitOps: o ConfigMap carrega o ARN da TARGET GROUP, não o do NLB. A asserção
# de igualdade contra module.ingress.target_group_arn seria unknown == unknown; o que dá para
# provar no plan é que a chave existe e vem de uma referência (a existência do conjunto exato
# de chaves está no composition.tftest.hcl). O valor certo é verificado no aceite, com o
# TargetGroupBinding registrando target de verdade.
run "o_configmap_declara_a_chave_da_target_group" {
  command = plan

  assert {
    condition     = contains(keys(kubernetes_config_map_v1.platform_bootstrap.data), "ingressTargetGroupArn")
    error_message = "sem ingressTargetGroupArn o TargetGroupBinding do GitOps nao tem o que nomear"
  }

  assert {
    condition     = contains(keys(kubernetes_config_map_v1.platform_bootstrap.data), "loadBalancerControllerRoleArn")
    error_message = "o chart do LBC vem por GitOps, mas o role e desta camada — sem a chave o Helm nao tem o que anotar"
  }
}

# 3.3 — as três pontas do nome da célula têm de concordar, e cada uma vive num lugar diferente:
# o certificado do ACM e a listener rule do ALB (conta network), e o `Gateway` CR do Istio
# (dentro do cluster). Divergir não quebra o apply: quebra o `curl` do aceite, com 404 do
# fixed-response do listener — que se lê como rota faltando no cluster.
run "o_host_de_entrada_cai_dentro_do_wildcard_da_celula" {
  command = plan

  assert {
    condition     = output.cell_ingress_fqdn == "*.control-plane.nonprod.exemplo.com"
    error_message = "o wildcard da celula: recebido ${output.cell_ingress_fqdn}"
  }

  # `services.`, nunca `app.` — qualquer outro nome sob o wildcard cai no fixed-response 404.
  assert {
    condition     = output.cell_services_url == "https://services.control-plane.nonprod.exemplo.com/"
    error_message = "a url de aceite: recebida ${output.cell_services_url}"
  }

  # E o `Gateway` CR do Istio tem de declarar o MESMO wildcard: o ALB aceita a conexão por
  # casar o certificado, mas quem decide se há rota é o Envoy, e ele só roteia host que o
  # Gateway declara.
  assert {
    condition     = toset(one(module.ingress_istio[*].gateway_hosts)) == toset([output.cell_ingress_fqdn])
    error_message = "os hosts do Gateway do Istio têm de ser o wildcard desta celula"
  }

  # E a listener rule do ALB tem de casar exatamente esse wildcard, senão a requisição nem
  # chega ao Envoy.
  assert {
    # `condition` e `host_header` são blocos repetíveis, logo SETs — `[0]` não compila
    # (documentado no CLAUDE.md desta pasta). Para bloco que existe uma vez só, o acesso é
    # `one(...)`.
    condition     = toset(one(one(aws_lb_listener_rule.cell.condition).host_header).values) == toset([output.cell_ingress_fqdn])
    error_message = "a listener rule do hub tem de casar o wildcard desta celula"
  }
}
