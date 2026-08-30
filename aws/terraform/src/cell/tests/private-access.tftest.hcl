# 2.4 + 2.5 — o caminho privado até a API do cluster.
#
# O 2.4 nasceu no plano como trabalho de DNS: associar a private hosted zone do endpoint do
# EKS à VPC hub. Esse caminho não existe — a doc do EKS é explícita: "Amazon EKS creates a
# Route 53 private hosted zone on your behalf (…) This private hosted zone is managed by
# Amazon EKS, and it doesn't appear in your account's Route 53 resources." Não há zona para
# ler nem para autorizar.
#
# E o plano B (Resolver inbound endpoint, ~US$ 0,25/h) é desnecessário: com o endpoint público
# desligado, "the cluster's API server endpoint is resolved by public DNS servers to a private
# IP address from the VPC". A resolução vem de graça, do DNS que o operador já usa.
#
# Sobra o que a doc prescreve para rede conectada por TGW: "You must ensure that your Amazon
# EKS control plane security group contains rules to allow ingress traffic on port 443 from
# your connected network."

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

  # O hub, por referencia — ver o comentario no variables.tf do modulo. hub_vpc_cidr_block
  # precisa ser CIDR real: alimenta a validacao client-side do provider na regra de 443 de
  # aws_vpc_security_group_ingress_rule.api_from_hub.
  hub_vpc_id                         = "vpc-hub000000000001"
  hub_vpc_cidr_block                 = "10.1.0.0/16"
  transit_gateway_id                 = "tgw-hub00000000001"
  hub_transit_gateway_route_table_id = "tgw-rtb-hub00000001"
  hub_transit_gateway_attachment_id  = "tgw-attach-hub00001"
  hub_alb_listener_arn               = "arn:aws:elasticloadbalancing:us-east-1:111111111111:listener/app/poc-hub-ingress/0000000000000001/aaaaaaaaaaaaaaaa"
  hub_alb_dns_name                   = "poc-hub-ingress-000000001.us-east-1.elb.amazonaws.com"
  hub_alb_zone_id                    = "Z35SXDOTRQ7X7K"
}

# As AZs vêm de data.aws_availability_zones (indexado por module.network); sob mock o valor é
# sintético e o plan morre — override em todo arquivo de teste da raiz.
override_data {
  target = data.aws_availability_zones.this
  values = {
    names = ["us-east-1a", "us-east-1b"]
  }
}

# --------------------------------------------------------------------------------------
# 2.5 — o endpoint público fecha por DEFAULT
# --------------------------------------------------------------------------------------

# Falha-fechado invertido em relação ao 1.2: lá o mecanismo era "variável sem default, quem
# aplica é obrigado a declarar o /32"; aqui é "o endpoint público simplesmente não existe a
# menos que alguém edite o tfvars". A segunda postura é estritamente mais forte, e é ela que
# fecha o Known Broken 3 — deixa de haver valor de tfvars que exponha a API ao mundo.
run "o_endpoint_publico_nasce_fechado" {
  command = plan

  assert {
    condition     = var.endpoint_public_access == false
    error_message = "o default de endpoint_public_access tem de ser false: com ele ligado, esquecer o valor no tfvars volta a expor a API"
  }

  assert {
    condition     = module.cluster.endpoint_public_access == false
    error_message = "o flag do root deveria chegar ao vpc_config do cluster, recebido ${module.cluster.endpoint_public_access}"
  }
}

# O caminho privado é o que sobra depois de fechar o público — se ele também estiver
# desligado, o cluster fica inalcançável de qualquer lugar e o apply do 2.5 morre no primeiro
# provider kubernetes.
run "o_endpoint_privado_continua_ligado" {
  command = plan

  assert {
    condition     = module.cluster.endpoint_private_access
    error_message = "sem endpoint privado, fechar o publico deixa o cluster inalcancavel"
  }
}

# Break-glass: ligar o endpoint público volta a exigir a lista, e ela tem de atravessar as
# duas camadas até o vpc_config.
run "ligar_o_endpoint_publico_volta_a_exigir_a_lista" {
  command = plan

  variables {
    endpoint_public_access = true
  }

  assert {
    condition     = module.cluster.public_access_cidrs == toset(["203.0.113.10/32"])
    error_message = "com o endpoint publico ligado o CIDR do root deveria chegar ao cluster, recebido ${jsonencode(module.cluster.public_access_cidrs)}"
  }
}

# --------------------------------------------------------------------------------------
# 2.4 — a regra de 443 a partir da rede conectada
# --------------------------------------------------------------------------------------

run "a_api_aceita_443_do_cidr_da_vpc_hub" {
  command = plan

  assert {
    condition     = aws_vpc_security_group_ingress_rule.api_from_hub.ip_protocol == "tcp"
    error_message = "recebido ${aws_vpc_security_group_ingress_rule.api_from_hub.ip_protocol}"
  }

  assert {
    condition     = aws_vpc_security_group_ingress_rule.api_from_hub.from_port == 443 && aws_vpc_security_group_ingress_rule.api_from_hub.to_port == 443
    error_message = "a regra e so para a porta da API, recebido ${aws_vpc_security_group_ingress_rule.api_from_hub.from_port}-${aws_vpc_security_group_ingress_rule.api_from_hub.to_port}"
  }

  # Não há asserção sobre EM QUE security group a regra entra, e a ausência é deliberada:
  # `cluster_security_group_id` é atributo computado pelo EKS, "known after apply" nos dois
  # lados da comparação, e o `terraform test` recusa condição sobre unknown. Overridar o
  # aws_eks_cluster inteiro para materializar o id substituiria os computados por inteiro
  # (armadilha já documentada em connectivity/) e traria mais ruído que verificação.
  #
  # O que sustenta a ligação sem teste: o SG que controla o endpoint privado é o do cluster,
  # e nenhum outro módulo desta camada expõe um security group para confundir.

  # A origem é o CIDR da VPC HUB, não o client CIDR do Client VPN: o Client VPN faz SNAT e o
  # pacote do operador chega à spoke com 10.1.x.x. Comprovado com ping no 2.3, e é o mesmo
  # motivo pelo qual não existe rota para 100.64.0.0/22 nesta camada.
  assert {
    condition     = aws_vpc_security_group_ingress_rule.api_from_hub.cidr_ipv4 == "10.1.0.0/16"
    error_message = "a origem deveria ser o CIDR da VPC hub, recebido ${aws_vpc_security_group_ingress_rule.api_from_hub.cidr_ipv4}"
  }

  assert {
    condition     = aws_vpc_security_group_ingress_rule.api_from_hub.cidr_ipv4 != var.vpc_cidr
    error_message = "a origem nao e o CIDR desta spoke: o trafego vem de fora, pelo TGW"
  }
}

# Um override de VALOR prova o valor; dois provam a LIGAÇÃO. Com um só, um
# `cidr_ipv4 = "10.1.0.0/16"` cravado no código passaria verde — foi exatamente o que
# aconteceu no 1.3 com os name servers. Segundo run, hub em outro /16: nenhuma constante
# satisfaz os dois. O que era `override_data` de `data.aws_vpc.hub` vira variavel do run —
# mesma prova, agora contra a interface fechada.
run "e_acompanha_um_hub_em_outro_cidr" {
  command = plan

  variables {
    hub_vpc_id         = "vpc-hub000000000002"
    hub_vpc_cidr_block = "10.7.0.0/16"
  }

  assert {
    condition     = aws_vpc_security_group_ingress_rule.api_from_hub.cidr_ipv4 == "10.7.0.0/16"
    error_message = "trocando a VPC hub lida, a regra deveria acompanhar — recebido ${aws_vpc_security_group_ingress_rule.api_from_hub.cidr_ipv4}"
  }
}

# ORDENAÇÃO, e o que este arquivo NÃO consegue provar: a regra tem de existir antes de
# qualquer recurso dos providers helm/kubernetes, porque é ela que abre o caminho por onde
# esses providers falam com o API server. A aresta está no `depends_on` dos módulos de helm
# e do ConfigMap — e `terraform test` não assere grafo (mesma limitação registrada em
# connectivity/ para aws_acm_certificate_validation). Sem a aresta o sintoma aparece só no
# apply, como timeout do primeiro release, não como falha de plan.
