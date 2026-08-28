variable "name" {
  description = "Prefixo dos recursos. Mesmo nome da celula (var.name da raiz)."
  type        = string
}

variable "vpc_id" {
  description = "VPC da spoke. O target group vive nela, e o NLB tambem."
  type        = string
}

variable "private_subnet_ids" {
  description = <<-EOT
    Subnets privadas onde o NLB ganha ENI. Uma por AZ, na MESMA ordem de
    private_subnet_cidrs — o par (id, cidr) do mesmo indice e o que produz cada
    subnet_mapping.
  EOT
  type        = list(string)
}

variable "private_subnet_cidrs" {
  description = <<-EOT
    CIDRs das mesmas subnets, na mesma ordem. Existem aqui porque o endereco do NLB e
    FIXADO com cidrhost(cidr, host_number) em vez de lido depois do apply: aws_lb nao expoe
    IP privado, e o caminho usual (cacar ENI por descricao) e fragil e so resolve depois de
    criar. Fixando, o hub pode apontar sua target group para um endereco conhecido em tempo
    de plan e estavel entre recriacoes do NLB.
  EOT
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_cidrs) == length(var.private_subnet_ids)
    error_message = "private_subnet_cidrs e private_subnet_ids tem de ter o mesmo tamanho — o indice pareia os dois."
  }

  validation {
    condition     = alltrue([for cidr in var.private_subnet_cidrs : can(cidrhost(cidr, 0))])
    error_message = "cada entrada de private_subnet_cidrs tem de ser um CIDR valido."
  }
}

variable "host_number" {
  description = <<-EOT
    Qual host de cada subnet o NLB ocupa. A AWS reserva os quatro primeiros enderecos de
    toda subnet (.0 a .3) e o ultimo, entao qualquer valor abaixo de 4 e recusado no apply
    com uma mensagem que nao explica a reserva.
  EOT
  type        = number
  default     = 10

  validation {
    condition     = var.host_number >= 4
    error_message = "host_number tem de ser >= 4: a AWS reserva os quatro primeiros enderecos de cada subnet."
  }
}

variable "allowed_ingress_cidrs" {
  description = <<-EOT
    Quem pode falar com o NLB. E o CIDR da VPC HUB, nao o client CIDR do Client VPN nem
    0.0.0.0/0: a decisao de ingress unico pelo hub diz que nenhuma spoke expoe acesso a si
    direto, e o Client VPN faz SNAT (o operador chega com IP do hub).
  EOT
  type        = list(string)

  validation {
    condition     = length(var.allowed_ingress_cidrs) > 0
    error_message = "sem CIDR liberado o NLB nasce inalcancavel — passar o CIDR da VPC hub."
  }

  validation {
    condition     = !contains(var.allowed_ingress_cidrs, "0.0.0.0/0")
    error_message = "0.0.0.0/0 contraria a decisao de ingress unico pelo hub: a spoke nao expoe acesso direto."
  }
}

variable "listener_port" {
  description = <<-EOT
    Porta do listener do NLB. O trecho hub->spoke e HTTP puro de proposito: o ALB nao valida
    certificado de backend, entao TLS aqui custaria gerencia sem ganhar verificacao. O TLS
    que o usuario ve termina no ALB, com o wildcard do ACM.
  EOT
  type        = number
  default     = 80
}

variable "target_port" {
  description = <<-EOT
    Porta do POD do ingress gateway, nao a do Service. Com target_type = ip quem registra e o
    LBC, resolvendo o targetPort do Service — declarar a porta certa aqui mantem o target group
    honesto sobre o que sera registrado, e e ela que o security group do cluster libera.

    80, nao 8080: o gateway do Istio escuta na porta que o Gateway CR declara, e o chart
    `gateway` do istio-release mapeia o Service 80 -> targetPort 80. O 8080 e do Istio antigo;
    com ele aqui o NLB tem egress para uma porta onde ninguem escuta, e o sintoma e "nenhum
    target saudavel" sem nada errado no cluster.
  EOT
  type        = number
  default     = 80
}

variable "health_check_port" {
  description = <<-EOT
    Porta de status do ingress gateway do Istio. Health check na porta de trafego passa a
    depender de existir um Gateway casando host, e um cluster sem VirtualService ficaria
    "unhealthy" sem nada estar errado; a porta de status responde independente de rota.
  EOT
  type        = number
  default     = 15021
}

variable "health_check_path" {
  description = "Endpoint de readiness do ingress gateway do Istio."
  type        = string
  default     = "/healthz/ready"
}

variable "tags" {
  description = "Tags aplicadas aos recursos do modulo."
  type        = map(string)
  default     = {}
}
