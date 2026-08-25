# mock_provider: nenhuma chamada à AWS, nenhuma credencial. `command = plan` avalia os
# locals e os argumentos dos recursos, que é onde vive a aritmética de CIDR.
mock_provider "aws" {}

variables {
  name               = "test"
  availability_zones = ["us-east-1a", "us-east-1b"]
}

run "divide_um_slash16_em_quatro_slash20" {
  command = plan

  variables {
    vpc_cidr = "10.1.0.0/16"
  }

  assert {
    condition     = aws_vpc.this.cidr_block == "10.1.0.0/16"
    error_message = "CIDR da VPC deveria ser 10.1.0.0/16, veio ${aws_vpc.this.cidr_block}"
  }

  assert {
    condition     = aws_subnet.public[0].cidr_block == "10.1.0.0/20"
    error_message = "public[0] deveria ser 10.1.0.0/20, veio ${aws_subnet.public[0].cidr_block}"
  }

  assert {
    condition     = aws_subnet.public[1].cidr_block == "10.1.16.0/20"
    error_message = "public[1] deveria ser 10.1.16.0/20, veio ${aws_subnet.public[1].cidr_block}"
  }

  assert {
    condition     = aws_subnet.private[0].cidr_block == "10.1.32.0/20"
    error_message = "private[0] deveria ser 10.1.32.0/20, veio ${aws_subnet.private[0].cidr_block}"
  }

  assert {
    condition     = aws_subnet.private[1].cidr_block == "10.1.48.0/20"
    error_message = "private[1] deveria ser 10.1.48.0/20, veio ${aws_subnet.private[1].cidr_block}"
  }
}

# Prova que a aritmética é derivada do CIDR e não hardcoded — é o gap da Composition de
# referência que este módulo existe para não herdar.
run "acompanha_um_cidr_diferente" {
  command = plan

  variables {
    vpc_cidr = "10.2.0.0/16"
  }

  assert {
    condition     = aws_subnet.public[0].cidr_block == "10.2.0.0/20"
    error_message = "trocar o CIDR deveria mover as subnets; public[0] veio ${aws_subnet.public[0].cidr_block}"
  }

  assert {
    condition     = aws_subnet.private[1].cidr_block == "10.2.48.0/20"
    error_message = "trocar o CIDR deveria mover as subnets; private[1] veio ${aws_subnet.private[1].cidr_block}"
  }
}

run "as_subnets_nao_se_sobrepoem" {
  command = plan

  variables {
    vpc_cidr = "10.1.0.0/16"
  }

  assert {
    condition = length(distinct(concat(
      aws_subnet.public[*].cidr_block,
      aws_subnet.private[*].cidr_block,
    ))) == 4
    error_message = "as 4 subnets deveriam ter CIDRs distintos"
  }
}

run "recusa_cidr_pequeno_demais" {
  command = plan

  variables {
    vpc_cidr = "10.1.0.0/24"
  }

  # Um /24 não cabe 4 subnets de /20 — a validação da variável tem de barrar antes do plan.
  expect_failures = [var.vpc_cidr]
}

run "recusa_numero_errado_de_azs" {
  command = plan

  variables {
    vpc_cidr           = "10.1.0.0/16"
    availability_zones = ["us-east-1a"]
  }

  expect_failures = [var.availability_zones]
}
