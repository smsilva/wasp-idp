# O invariante do plano, na forma executavel: nada em src/hub pode presumir a regiao. Duas
# execucoes com regioes diferentes tem que produzir nomes globais diferentes. Um run so nao
# distingue "veio da variavel" de "esta escrito no codigo".
#
# Os dois nomes globais sao o SAML provider (IAM e global por conta) e o FQDN da VPN (o record
# do Route 53 e um so para a Organization inteira). ACM e regional, mas o domain_name do
# certificado do VPN e o MESMO FQDN do record — dois certificados para o mesmo nome em regioes
# diferentes apontando para endpoints diferentes e como o record acaba sobrescrito. Um FQDN por
# regiao resolve os tres de uma vez.

mock_provider "aws" {}

variables {
  name               = "poc-hub"
  vpc_cidr           = "10.1.0.0/16"
  availability_zones = ["a", "b"]
  base_domain        = "exemplo.com"
  operator_group_ids = ["11111111-2222-3333-4444-555555555555"]
  saml_metadata_path = "tests/fixtures/saml-metadata.xml"
  spoke_account_ids  = ["222222222222"]
}

# Mesma razao dos outros arquivos: sem um arn valido, aws_ram_resource_association falha na
# validacao de schema do provider (client-side, sob mock) por um motivo que nada tem a ver com
# o que estes runs testam.
override_resource {
  target = aws_ec2_transit_gateway.hub
  values = {
    arn = "arn:aws:ec2:us-east-1:000000000000:transit-gateway/tgw-0000000000000000f"
  }
}

run "names_carry_us_east_1" {
  command = plan

  variables {
    region             = "us-east-1"
    availability_zones = ["us-east-1a", "us-east-1b"]
  }

  assert {
    condition     = aws_iam_saml_provider.client_vpn.name == "poc-hub-us-east-1-client-vpn"
    error_message = "SAML provider sem a regiao no nome: IAM e global, a segunda regiao colide."
  }

  assert {
    condition     = aws_acm_certificate.vpn.domain_name == "vpn.us-east-1.nonprod.exemplo.com"
    error_message = "FQDN da VPN sem a regiao: as duas regioes disputam o mesmo record do Route 53."
  }
}

run "names_carry_us_west_2" {
  command = plan

  variables {
    region             = "us-west-2"
    availability_zones = ["us-west-2a", "us-west-2b"]
  }

  assert {
    condition     = aws_iam_saml_provider.client_vpn.name == "poc-hub-us-west-2-client-vpn"
    error_message = "Nome identico ao do run anterior: a regiao esta escrita no codigo."
  }

  assert {
    condition     = aws_acm_certificate.vpn.domain_name == "vpn.us-west-2.nonprod.exemplo.com"
    error_message = "FQDN identico ao do run anterior: a regiao esta escrita no codigo."
  }
}
