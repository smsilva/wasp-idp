# O output existe para uma coisa só: o NLB interno do ingress (3.1) fixa o próprio endereço
# com cidrhost(<cidr da subnet privada>, N), em vez de ler IP privado de NLB depois do apply.
# O que precisa ser verdade, então, é (a) que os CIDRs são das PRIVADAS e (b) que estão na
# mesma ordem de private_subnet_ids — trocar por público ou desalinhar a ordem faria o
# subnet_mapping pedir um endereço que não pertence à subnet, e a AWS recusa no apply.
mock_provider "aws" {}

variables {
  name               = "test"
  availability_zones = ["us-east-1a", "us-east-1b"]
}

run "devolve_os_cidrs_das_privadas_na_ordem" {
  command = plan

  variables {
    vpc_cidr = "10.2.0.0/16"
  }

  assert {
    # join, não == contra literal: atributo list(string) comparado com literal ["a","b"] (que é
    # tuple) falha com "LHS and RHS values are of different types" em vez de comparar, e toset()
    # nos dois lados resolveria o tipo mas jogaria fora a ORDEM, que é justamente o que importa.
    condition     = join(",", output.private_subnet_cidrs) == "10.2.32.0/20,10.2.48.0/20"
    error_message = "esperado os dois /20 privados na ordem, veio ${jsonencode(output.private_subnet_cidrs)}"
  }

  # A ligação com os IDs: o índice i do output tem de descrever a MESMA subnet do índice i de
  # private_subnet_ids. Comparar com aws_subnet.private[*] é o que amarra os dois — sem isto,
  # um output que devolvesse as privadas em ordem invertida passaria pela asserção acima se os
  # valores literais fossem trocados junto.
  assert {
    condition = alltrue([
      for index, cidr in output.private_subnet_cidrs :
      cidr == aws_subnet.private[index].cidr_block
    ])
    error_message = "output desalinhado de aws_subnet.private — o índice tem de casar com private_subnet_ids"
  }

  # A consequência prática: o endereço que o NLB vai pedir pertence à subnet correspondente.
  assert {
    condition = alltrue([
      for index, cidr in output.private_subnet_cidrs :
      cidrhost(cidr, 10) == cidrhost(aws_subnet.private[index].cidr_block, 10)
    ])
    error_message = "cidrhost sobre o output tem de cair na mesma subnet privada do índice"
  }
}

# Segundo run com CIDR diferente: nenhuma lista fixa no código satisfaz os dois, então isto é
# o que distingue "derivado" de "hardcoded igual ao esperado" (Known Broken 14).
run "acompanha_um_cidr_diferente" {
  command = plan

  variables {
    vpc_cidr = "10.7.0.0/16"
  }

  assert {
    condition     = join(",", output.private_subnet_cidrs) == "10.7.32.0/20,10.7.48.0/20"
    error_message = "o output deveria acompanhar o CIDR da VPC, veio ${jsonencode(output.private_subnet_cidrs)}"
  }
}
