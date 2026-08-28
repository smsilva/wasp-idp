# O endereco do NLB e a interface com a fase 3.2: a target group do HUB registra estes IPs.
# Se eles nao forem determinados pelo par (subnet, cidr) do mesmo indice, o hub aponta para
# endereco que nao existe — e o sintoma aparece do outro lado da conta.
# Os runs sao `command = apply` (contra o mock, sem AWS): subnet_mapping e um set com
# atributos computados, entao no plan o set INTEIRO fica unknown e nenhuma assercao sobre o
# endereco avalia. Aplicar contra o mock torna o atributo do recurso legivel, o que e o que
# distingue "o local calculou certo" de "o valor chegou ao NLB".
#
# mock_resource...defaults, e nao override_resource: o ARN sintetico que o mock inventa
# ("ntyyuq7m") e recusado pela validacao client-side de load_balancer_arn no listener, mas
# override_resource substituiria os computados POR INTEIRO e levaria subnet_mapping junto —
# justamente o que se quer verificar. defaults preenche so o atributo nomeado.
mock_provider "aws" {
  mock_resource "aws_lb" {
    defaults = {
      arn = "arn:aws:elasticloadbalancing:us-east-1:111122223333:loadbalancer/net/test-ingress/0123456789abcdef"
    }
  }

  mock_resource "aws_lb_target_group" {
    defaults = {
      arn = "arn:aws:elasticloadbalancing:us-east-1:111122223333:targetgroup/test-ingress-gw/0123456789abcdef"
    }
  }
}

variables {
  name                  = "test"
  vpc_id                = "vpc-0123456789abcdef0"
  allowed_ingress_cidrs = ["10.1.0.0/16"]
}

# O modulo le o CIDR da VPC por data source para escrever o egress do SG, e cidr_ipv4 e um
# campo VALIDADO pelo schema do provider. Sob mock o data source devolveria uma string
# sintetica ("oz8pk32m"), a validacao client-side recusaria e o plan morreria por artefato de
# teste — nao por bug. Por isso o override em TODO run deste arquivo.
override_data {
  target = data.aws_vpc.this
  values = {
    cidr_block = "10.2.0.0/16"
  }
}

run "fixa_um_endereco_por_subnet_pelo_cidr_pareado" {
  command = apply

  variables {
    private_subnet_ids   = ["subnet-aaa", "subnet-bbb"]
    private_subnet_cidrs = ["10.2.32.0/20", "10.2.48.0/20"]
  }

  assert {
    condition     = length(aws_lb.ingress.subnet_mapping) == 2
    error_message = "esperado um subnet_mapping por subnet privada, veio ${length(aws_lb.ingress.subnet_mapping)}"
  }

  # subnet_mapping e um SET no schema do provider — indexar com [0] nao compila
  # ("set elements do not have addressable keys"). A comparacao e entre conjuntos.
  assert {
    condition = toset([
      for mapping in aws_lb.ingress.subnet_mapping :
      "${mapping.subnet_id}=${mapping.private_ipv4_address}"
      ]) == toset([
      "subnet-aaa=10.2.32.10",
      "subnet-bbb=10.2.48.10",
    ])
    error_message = "cada subnet tem de receber o host 10 do PROPRIO cidr; veio ${jsonencode([for m in aws_lb.ingress.subnet_mapping : "${m.subnet_id}=${m.private_ipv4_address}"])}"
  }

  # A garantia que o hub depende: os IPs do output sao os mesmos do subnet_mapping.
  assert {
    condition = toset(output.private_ips) == toset([
      for mapping in aws_lb.ingress.subnet_mapping : mapping.private_ipv4_address
    ])
    error_message = "private_ips tem de ser exatamente os enderecos do subnet_mapping"
  }
}

# Segundo run com CIDRs e TAMANHO diferentes: nenhuma lista fixa no codigo satisfaz os dois,
# o que distingue "calculado" de "hardcoded igual ao esperado" (Known Broken 14).
run "acompanha_outro_cidr_e_outra_quantidade_de_azs" {
  command = apply

  variables {
    private_subnet_ids   = ["subnet-x", "subnet-y", "subnet-z"]
    private_subnet_cidrs = ["10.9.0.0/24", "10.9.1.0/24", "10.9.2.0/24"]
    host_number          = 7
  }

  assert {
    condition = toset([
      for mapping in aws_lb.ingress.subnet_mapping :
      "${mapping.subnet_id}=${mapping.private_ipv4_address}"
      ]) == toset([
      "subnet-x=10.9.0.7",
      "subnet-y=10.9.1.7",
      "subnet-z=10.9.2.7",
    ])
    error_message = "o endereco tem de seguir o cidr e o host_number, veio ${jsonencode([for m in aws_lb.ingress.subnet_mapping : "${m.subnet_id}=${m.private_ipv4_address}"])}"
  }
}

run "o_nlb_e_interno_com_security_group_e_cross_zone" {
  command = apply

  variables {
    private_subnet_ids   = ["subnet-aaa", "subnet-bbb"]
    private_subnet_cidrs = ["10.2.32.0/20", "10.2.48.0/20"]
  }

  # A propriedade central do desenho: nenhuma spoke expoe acesso a si direto na internet.
  assert {
    condition     = aws_lb.ingress.internal
    error_message = "o NLB tem de ser interno — ingress e unico e passa pelo hub"
  }

  assert {
    condition     = aws_lb.ingress.load_balancer_type == "network"
    error_message = "tem de ser NLB: o ALB do hub aponta para IPs fixos, e so NLB tem endereco fixavel"
  }

  # Irreversivel: NLB criado sem SG nunca pode ganhar um depois (doc do ELB). Esta assercao
  # existe para que remover o SG do codigo seja um teste vermelho, e nao a descoberta de que
  # o load balancer precisa ser recriado.
  assert {
    condition     = length(aws_lb.ingress.security_groups) == 1
    error_message = "o NLB tem de nascer com security group — nao ha como acrescentar depois"
  }

  # Sem cross-zone, com o gateway numa AZ so, metade dos IPs fixos que o hub registra fica
  # sem target saudavel e o hub ve 50% de falha sem nada errado no cluster.
  assert {
    condition     = aws_lb.ingress.enable_cross_zone_load_balancing
    error_message = "cross-zone tem de estar ligado: o hub registra os DOIS IPs fixos"
  }
}

run "so_o_hub_alcanca_o_nlb_e_so_na_porta_do_listener" {
  command = apply

  variables {
    private_subnet_ids   = ["subnet-aaa", "subnet-bbb"]
    private_subnet_cidrs = ["10.2.32.0/20", "10.2.48.0/20"]
    allowed_ingress_cidrs = [
      "10.1.0.0/16",
      "10.3.0.0/16",
    ]
  }

  assert {
    condition = toset([
      for rule in values(aws_vpc_security_group_ingress_rule.from_hub) : rule.cidr_ipv4
      ]) == toset([
      "10.1.0.0/16",
      "10.3.0.0/16",
    ])
    error_message = "as regras de ingress tem de ser exatamente os CIDRs autorizados"
  }

  assert {
    condition = alltrue([
      for rule in values(aws_vpc_security_group_ingress_rule.from_hub) :
      rule.from_port == 80 && rule.to_port == 80 && rule.ip_protocol == "tcp"
    ])
    error_message = "o ingress tem de abrir so a porta do listener, em tcp"
  }
}
