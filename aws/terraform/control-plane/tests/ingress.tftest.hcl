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
  network_profile     = "network"
  hub_vpc_name        = "poc-hub-vpc"
  vpc_cidr            = "10.2.0.0/16"
  availability_zones  = ["us-east-1a", "us-east-1b"]
  target_account_ids  = ["000000000000"]
  network_account_id  = "111111111111"
  public_access_cidrs = ["203.0.113.10/32"]
}

# Mesmo motivo do private-access.tftest.hcl: sob mock o cidr_block vem sintético e a validação
# client-side do provider recusa o valor na regra de 443. Aqui o override tem um segundo papel
# — é o CIDR hub que vira allowed_ingress_cidrs do NLB.
override_data {
  target = data.aws_vpc.hub
  values = {
    id         = "vpc-hub000000000001"
    cidr_block = "10.1.0.0/16"
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
    condition     = length(module.ingress.private_ips) == length(var.availability_zones)
    error_message = "um endereco por AZ, recebido ${length(module.ingress.private_ips)} para ${length(var.availability_zones)} AZs"
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
    condition     = aws_vpc_security_group_ingress_rule.gateway_from_nlb.from_port == 8080 && aws_vpc_security_group_ingress_rule.gateway_from_nlb.to_port == 8080
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
