mock_provider "aws" {}

variables {
  name               = "test"
  vpc_cidr           = "10.1.0.0/16"
  availability_zones = ["us-east-1a", "us-east-1b"]
  enable_nat_gateway = false
}

# As tags de papel são o ÚNICO caminho de auto-discovery do AWS Load Balancer Controller: ele
# não examina route table para deduzir se a subnet é pública ou privada (o controller in-tree
# examina; o LBC não). Sem elas o LBC não acha onde criar load balancer, e o sintoma é obscuro
# — daí valer teste, e não só o comentário no main.tf.
#
# A tag kubernetes.io/cluster/<nome> NÃO entra: é opcional a partir do LBC 2.1.2 e só serve
# para escolher entre clusters que compartilham a VPC. Aqui é um cluster por VPC spoke, e o
# módulo não conhece nome de cluster — acrescentá-la criaria dependência network → cluster.

run "as_subnets_publicas_carregam_a_tag_de_elb_externo" {
  command = plan

  # alltrue([]) é true: sem esta contagem, a assertion seguinte passaria com zero subnets.
  assert {
    condition     = length(aws_subnet.public) == 2
    error_message = "deveriam existir 2 subnets públicas, há ${length(aws_subnet.public)}"
  }

  assert {
    condition = alltrue([
      for s in aws_subnet.public : lookup(s.tags, "kubernetes.io/role/elb", null) == "1"
    ])
    error_message = "toda subnet pública precisa de kubernetes.io/role/elb = 1 para o LBC criar load balancer internet-facing"
  }
}

run "as_subnets_privadas_carregam_a_tag_de_elb_interno" {
  command = plan

  assert {
    condition     = length(aws_subnet.private) == 2
    error_message = "deveriam existir 2 subnets privadas, há ${length(aws_subnet.private)}"
  }

  assert {
    condition = alltrue([
      for s in aws_subnet.private : lookup(s.tags, "kubernetes.io/role/internal-elb", null) == "1"
    ])
    error_message = "toda subnet privada precisa de kubernetes.io/role/internal-elb = 1 — é onde nasce o NLB interno do ingress"
  }
}

# As duas assertions acima passariam se as tags fossem aplicadas às DUAS famílias de subnet
# (um merge desatento no lugar errado). Aí o LBC acharia candidata pública para um load
# balancer interno e vice-versa — pior que a ausência, porque falha em runtime e não no apply.
run "as_tags_de_papel_nao_se_cruzam" {
  command = plan

  assert {
    condition = alltrue([
      for s in aws_subnet.public : lookup(s.tags, "kubernetes.io/role/internal-elb", null) == null
    ])
    error_message = "subnet pública não pode carregar internal-elb: ela viraria candidata a load balancer interno"
  }

  assert {
    condition = alltrue([
      for s in aws_subnet.private : lookup(s.tags, "kubernetes.io/role/elb", null) == null
    ])
    error_message = "subnet privada não pode carregar elb: ela viraria candidata a load balancer internet-facing sem rota para o IGW"
  }
}

# var.tags é o canal de tag de quem chama o módulo. Um merge na ordem errada deixaria o
# chamador sobrescrever silenciosamente as tags de papel — e a quebra só apareceria na fase
# de ingress, longe da causa.
run "tags_do_chamador_convivem_com_as_tags_de_papel" {
  command = plan

  variables {
    tags = {
      Environment = "test"
      # Colide de propósito com a tag de papel, e com o valor ERRADO: é o que distingue
      # merge(var.tags, {papel}) de merge({papel}, var.tags). Sem a colisão, inverter a
      # ordem do merge passaria por este teste sem ser notado.
      "kubernetes.io/role/elb" = "0"
    }
  }

  assert {
    condition = alltrue([
      for s in aws_subnet.public : lookup(s.tags, "kubernetes.io/role/elb", null) == "1"
    ])
    error_message = "var.tags não pode derrubar kubernetes.io/role/elb — o merge tem de ter as tags de papel do lado que vence"
  }

  assert {
    condition = alltrue([
      for s in aws_subnet.private : lookup(s.tags, "kubernetes.io/role/internal-elb", null) == "1"
    ])
    error_message = "var.tags não pode derrubar kubernetes.io/role/internal-elb"
  }

  assert {
    condition = alltrue([
      for s in concat(aws_subnet.public, aws_subnet.private) :
      lookup(s.tags, "Environment", null) == "test" && lookup(s.tags, "Name", null) != null
    ])
    error_message = "as tags do chamador e o Name deveriam sobreviver ao merge das tags de papel"
  }
}
