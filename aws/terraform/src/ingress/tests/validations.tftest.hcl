# Cada uma destas recusas existe porque o erro equivalente da AWS chega tarde e nao explica a
# causa: endereco fora da subnet, endereco reservado, ou um NLB alcancavel de qualquer lugar.
mock_provider "aws" {}

variables {
  name                  = "test"
  vpc_id                = "vpc-0123456789abcdef0"
  private_subnet_ids    = ["subnet-aaa", "subnet-bbb"]
  private_subnet_cidrs  = ["10.2.32.0/20", "10.2.48.0/20"]
  allowed_ingress_cidrs = ["10.1.0.0/16"]
}

override_data {
  target = data.aws_vpc.this
  values = {
    cidr_block = "10.2.0.0/16"
  }
}

# Listas de tamanhos diferentes desalinhariam o par (subnet, cidr): o endereco calculado
# cairia numa subnet que nao e a do mapping, e a AWS recusaria com "the specified address is
# not in the subnet" sem dizer que a causa e o pareamento.
run "recusa_listas_de_tamanhos_diferentes" {
  command = plan

  variables {
    private_subnet_cidrs = ["10.2.32.0/20"]
  }

  expect_failures = [var.private_subnet_cidrs]
}

run "recusa_cidr_malformado" {
  command = plan

  variables {
    private_subnet_cidrs = ["10.2.32.0/20", "nao-e-cidr"]
  }

  expect_failures = [var.private_subnet_cidrs]
}

# A AWS reserva .0 a .3 de toda subnet. Pedir host 2 falha no apply, depois de o SG e a
# target group ja terem sido criados.
run "recusa_host_reservado_pela_aws" {
  command = plan

  variables {
    host_number = 2
  }

  expect_failures = [var.host_number]
}

# A propriedade que o desenho inteiro sustenta: nenhuma spoke expoe acesso a si direto na
# internet. Um 0.0.0.0/0 aqui passaria em qualquer teste de forma e destruiria a decisao.
run "recusa_abrir_o_nlb_para_a_internet" {
  command = plan

  variables {
    allowed_ingress_cidrs = ["10.1.0.0/16", "0.0.0.0/0"]
  }

  expect_failures = [var.allowed_ingress_cidrs]
}

run "recusa_nlb_sem_ninguem_autorizado" {
  command = plan

  variables {
    allowed_ingress_cidrs = []
  }

  expect_failures = [var.allowed_ingress_cidrs]
}
