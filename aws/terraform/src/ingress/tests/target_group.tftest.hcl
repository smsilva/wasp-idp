# A target group e o contrato com o cluster: o TargetGroupBinding do LBC registra os pods
# nela. Tipo, protocolo e health check errados aqui produzem sintoma dentro do cluster ("o
# gateway esta de pe e o hub diz que nao"), longe da causa.
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
  private_subnet_ids    = ["subnet-aaa", "subnet-bbb"]
  private_subnet_cidrs  = ["10.2.32.0/20", "10.2.48.0/20"]
}

override_data {
  target = data.aws_vpc.this
  values = {
    cidr_block = "10.2.0.0/16"
  }
}

run "registra_por_ip_para_o_lbc_poder_ligar_os_pods" {
  command = apply

  # target_type = ip e o que permite o NLB existir ANTES do workload: o LBC registra IP de
  # pod nela depois, por TargetGroupBinding. Com "instance" o alvo seria o nodegroup e o
  # TargetGroupBinding nao teria o que fazer.
  assert {
    condition     = aws_lb_target_group.gateway.target_type == "ip"
    error_message = "target_type tem de ser ip — e o que o TargetGroupBinding registra"
  }

  assert {
    condition     = aws_lb_target_group.gateway.protocol == "TCP"
    error_message = "o NLB fala TCP; protocolo de target group diferente disso nem casa com o listener"
  }

  # A porta do POD, nao a do Service.
  assert {
    condition     = aws_lb_target_group.gateway.port == 8080
    error_message = "a porta da target group tem de ser a do pod do gateway, veio ${aws_lb_target_group.gateway.port}"
  }

  assert {
    condition     = aws_lb_target_group.gateway.vpc_id == "vpc-0123456789abcdef0"
    error_message = "a target group tem de viver na VPC da spoke"
  }
}

run "o_health_check_pergunta_a_porta_de_status_por_http" {
  command = apply

  # health_check e um bloco de lista de um elemento no schema — one() e o acesso, e um
  # `[0]` funcionaria aqui mas quebraria se o provider mudasse para set.
  assert {
    condition     = one(aws_lb_target_group.gateway.health_check).protocol == "HTTP"
    error_message = "health check TCP diria 'saudavel' para um Envoy sem nenhuma rota — tem de ser HTTP"
  }

  assert {
    condition     = one(aws_lb_target_group.gateway.health_check).port == "15021"
    error_message = "o health check tem de ir a porta de STATUS do gateway, veio ${one(aws_lb_target_group.gateway.health_check).port}"
  }

  assert {
    condition     = one(aws_lb_target_group.gateway.health_check).path == "/healthz/ready"
    error_message = "o path tem de ser o readiness do Istio"
  }

  # A porta do health check nao pode ser a de trafego: se fossem iguais, a assercao acima
  # passaria por coincidencia e o teste nao distinguiria os dois papeis.
  assert {
    condition     = one(aws_lb_target_group.gateway.health_check).port != tostring(aws_lb_target_group.gateway.port)
    error_message = "health check e trafego tem de usar portas distintas"
  }
}

run "o_listener_encaminha_para_a_target_group_do_gateway" {
  command = apply

  assert {
    condition     = aws_lb_listener.ingress.port == 80
    error_message = "o listener escuta na porta do trecho hub->spoke (HTTP puro), veio ${aws_lb_listener.ingress.port}"
  }

  assert {
    condition     = aws_lb_listener.ingress.protocol == "TCP"
    error_message = "listener de NLB e TCP"
  }

  # A ligacao: o listener aponta para ESTA target group, nao para outra qualquer.
  assert {
    condition     = one(aws_lb_listener.ingress.default_action).target_group_arn == aws_lb_target_group.gateway.arn
    error_message = "o listener tem de encaminhar para a target group do gateway"
  }

  assert {
    condition     = aws_lb_listener.ingress.load_balancer_arn == aws_lb.ingress.arn
    error_message = "o listener tem de pertencer ao NLB deste modulo"
  }
}

run "o_output_entrega_o_arn_da_target_group_nao_o_do_nlb" {
  command = apply

  # O ConfigMap platform-bootstrap carrega ingressTargetGroupArn. Entregar o ARN do NLB aqui
  # daria um TargetGroupBinding que sincroniza para sempre sem registrar nada.
  assert {
    condition     = output.target_group_arn == aws_lb_target_group.gateway.arn
    error_message = "target_group_arn tem de ser o ARN da target group, nao o do load balancer"
  }

  assert {
    condition     = output.security_group_id == aws_security_group.nlb.id
    error_message = "security_group_id tem de ser o SG do NLB — e o que o TargetGroupBinding nomeia como origem"
  }
}
