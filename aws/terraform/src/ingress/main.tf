locals {
  # Os enderecos, em lista propria e nao so dentro do mapa abaixo: o mapa e chaveado por id de
  # subnet, que e computado, e isso torna o mapa INTEIRO unknown no plan — inclusive os valores,
  # que sao puro calculo. Derivar a lista direto dos CIDRs mantem o output legivel no plan, que
  # e o que permite a fase 3.2 (target group do hub) ser escrita sem esperar o NLB existir.
  private_ips = [for cidr in var.private_subnet_cidrs : cidrhost(cidr, var.host_number)]

  # O par (subnet, endereco fixo) de cada AZ. Indice pareia as duas listas — a validacao de
  # tamanho em variables.tf e o que impede um desalinhamento silencioso, que aqui produziria
  # um endereco fora da subnet e um erro de apply que nao diz "as listas nao casam".
  subnet_mappings = {
    for index, subnet_id in var.private_subnet_ids : subnet_id => local.private_ips[index]
  }
}

# O NLB nasce COM security group, e isso e irreversivel: pela doc do ELB, "if the Network Load
# Balancer was created without security groups, it can't support security groups after
# creation" — nao ha como acrescentar depois, so recriando. Ter o SG e o que faz a decisao de
# "ingress unico pelo hub" valer na rede, e nao so no desenho: quem nao vem do hub nao
# completa handshake, independente do que o mesh decida.
resource "aws_security_group" "nlb" {
  name        = "${var.name}-ingress-nlb"
  description = "Internal ingress NLB: only the hub may reach it"
  vpc_id      = var.vpc_id

  tags = merge(var.tags, { Name = "${var.name}-ingress-nlb" })

  lifecycle {
    # O SG nao pode ser destruido enquanto estiver anexado ao NLB, e o NLB nao pode trocar de
    # SG — criar o substituto antes de soltar o antigo e o que permite mudar a regra sem
    # recriar o load balancer (e sem perder os enderecos fixos que o hub referencia).
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_ingress_rule" "from_hub" {
  for_each = toset(var.allowed_ingress_cidrs)

  security_group_id = aws_security_group.nlb.id
  description       = "Ingress traffic from the hub VPC"

  cidr_ipv4   = each.value
  ip_protocol = "tcp"
  from_port   = var.listener_port
  to_port     = var.listener_port
}

# Saida para os pods do gateway. Com target_type = ip o NLB reescreve o IP de destino e fala
# com o pod pelo endereco dele, dentro desta mesma VPC — por isso o egress e o CIDR da VPC, e
# nao "todo lugar".
resource "aws_vpc_security_group_egress_rule" "to_targets" {
  security_group_id = aws_security_group.nlb.id
  description       = "Reach the ingress gateway pods"

  cidr_ipv4   = data.aws_vpc.this.cidr_block
  ip_protocol = "tcp"
  from_port   = var.target_port
  to_port     = var.target_port
}

# O health check sai da mesma ENI, para outra porta — sem esta regra o target group fica
# unhealthy para sempre e o sintoma (nenhum target saudavel) nao aponta para o egress.
resource "aws_vpc_security_group_egress_rule" "health_check" {
  security_group_id = aws_security_group.nlb.id
  description       = "Health check the ingress gateway status port"

  cidr_ipv4   = data.aws_vpc.this.cidr_block
  ip_protocol = "tcp"
  from_port   = var.health_check_port
  to_port     = var.health_check_port
}

data "aws_vpc" "this" {
  id = var.vpc_id
}

resource "aws_lb" "ingress" {
  name               = "${var.name}-ingress"
  load_balancer_type = "network"
  internal           = true
  security_groups    = [aws_security_group.nlb.id]

  dynamic "subnet_mapping" {
    for_each = local.subnet_mappings

    content {
      subnet_id            = subnet_mapping.key
      private_ipv4_address = subnet_mapping.value
    }
  }

  # Cross-zone LIGADO, ao contrario do default do NLB. Sem isto, cada no do NLB so alcanca
  # targets da propria AZ: com o gateway rodando numa AZ so — o normal com 1 replica —, o no
  # da outra AZ nao tem nenhum target saudavel, e a target group do hub, que aponta para os
  # DOIS enderecos fixos, veria metade dos seus targets falhando sem nada estar errado no
  # cluster. Custo: trafego cross-AZ, irrelevante nesta escala.
  enable_cross_zone_load_balancing = true

  tags = merge(var.tags, { Name = "${var.name}-ingress" })
}

# O target group nasce VAZIO de proposito: quem registra os pods e o TargetGroupBinding do
# LBC, do lado do GitOps. A doc do LBC descreve exatamente este caso — provisionar o load
# balancer "completely outside of Kubernetes" e ainda gerenciar os targets pelo Service. E o
# que permite o apply unico: se o LBC criasse o NLB, o ARN so existiria depois do workload.
resource "aws_lb_target_group" "gateway" {
  # name_prefix, nao name: trocar port ou target_type forca RECRIACAO, e ai o nome fixo cria um
  # impasse sem saida boa. Sem create_before_destroy o Terraform tenta apagar a target group
  # antes de reapontar o listener e a AWS recusa com ResourceInUse; com create_before_destroy e
  # nome fixo, recusa a nova com "already exists". Com prefixo, a AWS gera o sufixo, a nova
  # nasce ao lado da velha, o listener passa a apontar para ela e so entao a velha morre.
  #
  # O preco e o nome ilegivel: target group aceita no maximo 6 caracteres de prefixo. O nome
  # legivel vive na tag Name, e quem consome a target group usa o ARN (ConfigMap
  # platform-bootstrap), nao o nome. Os dois sintomas acima foram vistos de verdade ao trocar a
  # porta do gateway de 8080 para 80.
  name_prefix = substr(var.name, 0, 6)
  vpc_id      = var.vpc_id
  target_type = "ip"
  protocol    = "TCP"
  port        = var.target_port

  # Health check HTTP na porta de STATUS, nao TCP na porta de trafego: um handshake TCP com o
  # Envoy responde antes de existir qualquer rota, entao TCP diria "saudavel" para um gateway
  # que devolveria 404 em tudo. /healthz/ready responde pela prontidao real do proxy.
  health_check {
    protocol            = "HTTP"
    port                = tostring(var.health_check_port)
    path                = var.health_check_path
    healthy_threshold   = 2
    unhealthy_threshold = 2
    interval            = 10
  }

  # Client IP preservation fica no default (DESLIGADO para target group de tipo IP com
  # protocolo TCP, conforme a doc do ELB) e isto e deliberado: o pod ve o IP do no do NLB, e o
  # IP do usuario chega por X-Forwarded-For do ALB. Ligar aqui faria o pacote chegar com o IP
  # do ALB do hub, que nao e o do usuario tampouco — trocaria um proxy por outro e ainda
  # obrigaria o SG dos pods a liberar CIDR de outra conta.
  tags = merge(var.tags, { Name = "${var.name}-ingress-gw" })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_lb_listener" "ingress" {
  load_balancer_arn = aws_lb.ingress.arn
  protocol          = "TCP"
  port              = var.listener_port

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.gateway.arn
  }
}
