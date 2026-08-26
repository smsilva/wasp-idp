mock_provider "aws" {}

variables {
  name               = "test"
  vpc_cidr           = "10.1.0.0/16"
  availability_zones = ["us-east-1a", "us-east-1b"]
}

run "com_nat_ligado_cria_os_16_recursos_da_l1a" {
  command = plan

  variables {
    enable_nat_gateway = true
  }

  # IDs de subnet só existem depois do apply, então uma comparação entre eles não é
  # avaliável sob `command = plan`. Os overrides dão IDs conhecidos e DISTINTOS — distintos
  # de propósito: com o mesmo ID para as duas, a assertion passaria mesmo se o NAT fosse
  # posto na subnet privada, e o teste não valeria nada.
  override_resource {
    target          = aws_subnet.public[0]
    override_during = plan
    values          = { id = "subnet-public-0" }
  }

  override_resource {
    target          = aws_subnet.private[0]
    override_during = plan
    values          = { id = "subnet-private-0" }
  }

  assert {
    condition     = length(aws_eip.nat) == 1
    error_message = "com NAT ligado deveria haver 1 EIP, há ${length(aws_eip.nat)}"
  }

  assert {
    condition     = length(aws_nat_gateway.this) == 1
    error_message = "com NAT ligado deveria haver 1 NAT Gateway, há ${length(aws_nat_gateway.this)}"
  }

  assert {
    condition     = length(aws_route.private_default) == 1
    error_message = "a route table privada deveria ter rota default via NAT"
  }

  assert {
    condition     = aws_route.private_default[0].destination_cidr_block == "0.0.0.0/0"
    error_message = "a rota privada deveria ser 0.0.0.0/0"
  }

  # O NAT tem de nascer numa subnet PÚBLICA — numa privada ele não alcança o IGW.
  assert {
    condition     = aws_nat_gateway.this[0].subnet_id == "subnet-public-0"
    error_message = "o NAT Gateway deveria estar na primeira subnet pública, está em ${aws_nat_gateway.this[0].subnet_id}"
  }
}

run "com_nat_desligado_nao_cria_nem_nat_nem_rota_privada" {
  command = plan

  variables {
    enable_nat_gateway = false
  }

  assert {
    condition     = length(aws_nat_gateway.this) == 0
    error_message = "com NAT desligado não deveria haver NAT Gateway"
  }

  assert {
    condition     = length(aws_eip.nat) == 0
    error_message = "com NAT desligado não deveria haver EIP — é o que mantém o custo em zero"
  }

  assert {
    condition     = length(aws_route.private_default) == 0
    error_message = "sem NAT não há rota default privada possível"
  }

  # O IGW e a rota pública existem nos dois casos.
  assert {
    condition     = aws_route.public_default.destination_cidr_block == "0.0.0.0/0"
    error_message = "a rota pública default deveria existir mesmo sem NAT"
  }
}

run "toda_subnet_esta_associada_a_uma_route_table" {
  command = plan

  variables {
    enable_nat_gateway = true
  }

  assert {
    condition     = length(aws_route_table_association.public) == 2
    error_message = "as 2 subnets públicas deveriam estar associadas"
  }

  assert {
    condition     = length(aws_route_table_association.private) == 2
    error_message = "as 2 subnets privadas deveriam estar associadas"
  }
}

# O 2.3 (attachment do spoke no TGW) precisa acrescentar rota nas duas pontas — hub e spoke —
# em direção ao TGW, e a route table privada é única (compartilhada por todas as subnets
# privadas). Sem o output, quem consome o módulo não tem como referenciá-la.
run "o_id_da_route_table_privada_e_exposto" {
  command = plan

  # id só existe depois do apply; o override dá um valor conhecido no plan.
  override_resource {
    target          = aws_route_table.private
    override_during = plan
    values          = { id = "rtb-private-test" }
  }

  assert {
    condition     = output.private_route_table_id == "rtb-private-test"
    error_message = "private_route_table_id deveria expor aws_route_table.private.id, recebido ${output.private_route_table_id}"
  }
}
