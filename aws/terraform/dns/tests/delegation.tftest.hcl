mock_provider "aws" {}
mock_provider "azurerm" {}

variables {
  base_domain              = "exemplo.com"
  azure_subscription_id    = "00000000-0000-0000-0000-000000000000"
  azure_dns_resource_group = "rg-dns"
}

run "a_subzona_e_delegada_nao_o_apex" {
  command = plan

  assert {
    condition     = aws_route53_zone.subzone.name == "nonprod.exemplo.com"
    error_message = "a zona criada deveria ser a subzona, recebido ${aws_route53_zone.subzone.name}"
  }

  # A garantia que importa é negativa: o apex continua no Azure DNS. Se esta raiz criasse a
  # zona do apex, a resolução do domínio inteiro passaria a depender dela.
  assert {
    condition     = aws_route53_zone.subzone.name != "exemplo.com"
    error_message = "esta raiz não pode criar a zona do apex — ele fica no Azure DNS"
  }
}

# O ponto do passo: a delegação é código. Um NS na pai apontando para os name servers que a
# AWS acabou de dar, sem copiar e colar valor entre clouds.
run "o_ns_da_pai_aponta_para_os_name_servers_da_subzona" {
  command = plan

  assert {
    condition     = length(azurerm_dns_ns_record.delegation) == 1
    error_message = "com manage_delegation ligado deveria haver 1 registro NS, há ${length(azurerm_dns_ns_record.delegation)}"
  }

  assert {
    condition     = azurerm_dns_ns_record.delegation[0].zone_name == "exemplo.com"
    error_message = "o NS entra na zona PAI, recebido ${azurerm_dns_ns_record.delegation[0].zone_name}"
  }

  assert {
    condition     = azurerm_dns_ns_record.delegation[0].name == "nonprod"
    error_message = "o nome do registro é o rótulo da subzona, recebido ${azurerm_dns_ns_record.delegation[0].name}"
  }

  # TTL curto é o que permite recriar a subzona e ver a delegação nova pegar em minutos.
  assert {
    condition     = azurerm_dns_ns_record.delegation[0].ttl == 300
    error_message = "TTL deveria ser 300, recebido ${azurerm_dns_ns_record.delegation[0].ttl}"
  }
}

# As duas asserções que provam o passo — e são DUAS de propósito.
#
# name_servers só existe depois do apply, então sem override não há o que comparar. Mas um
# override só não basta: com uma lista fixa no main.tf igual aos valores injetados, a
# asserção passaria mesmo sem fio nenhum. Foi exatamente o que aconteceu na primeira versão
# deste teste — a mutação que colava os name servers à mão passou verde.
#
# Com DOIS overrides de valores diferentes, nenhuma lista fixa satisfaz os dois: ou o
# `records` acompanha o atributo da zona, ou um dos runs cai.

run "os_records_acompanham_os_name_servers_da_subzona" {
  command = plan

  override_resource {
    target          = aws_route53_zone.subzone
    override_during = plan
    values = {
      name_servers = ["ns-1.awsdns-00.com", "ns-2.awsdns-00.net"]
    }
  }

  assert {
    # toset() nos DOIS lados: `records` é list(string) e o literal é tuple, e o == entre eles
    # falha com "LHS and RHS values are of different types" em vez de comparar. Conjunto
    # também é a semântica certa — a ordem dos name servers de um NS não significa nada.
    condition = toset(azurerm_dns_ns_record.delegation[0].records) == toset([
      "ns-1.awsdns-00.com", "ns-2.awsdns-00.net"
    ])
    error_message = "os records do NS deveriam vir de aws_route53_zone.subzone.name_servers, recebido ${jsonencode(azurerm_dns_ns_record.delegation[0].records)}"
  }
}

run "e_acompanham_outro_conjunto_de_name_servers" {
  command = plan

  override_resource {
    target          = aws_route53_zone.subzone
    override_during = plan
    values = {
      name_servers = ["ns-9.awsdns-99.org", "ns-8.awsdns-88.co.uk", "ns-7.awsdns-77.net"]
    }
  }

  # Três, não dois: o tamanho também tem de acompanhar. Uma lista fixa de dois elementos
  # falharia aqui mesmo se por acaso casasse com o run anterior.
  assert {
    condition = toset(azurerm_dns_ns_record.delegation[0].records) == toset([
      "ns-9.awsdns-99.org", "ns-8.awsdns-88.co.uk", "ns-7.awsdns-77.net"
    ])
    error_message = "trocando os name servers da zona, os records do NS deveriam trocar junto — recebido ${jsonencode(azurerm_dns_ns_record.delegation[0].records)}"
  }
}

# Numa raiz com dois providers, sem credencial do segundo o plan falha mesmo para mudança que
# só toca o primeiro. Este é o interruptor que permite trabalhar o lado AWS sozinho — e ele
# precisa funcionar SEM os valores do Azure, senão não serve para nada.
run "sem_delegacao_o_azure_nao_e_tocado" {
  command = plan

  variables {
    manage_delegation        = false
    azure_subscription_id    = null
    azure_dns_resource_group = null
  }

  assert {
    condition     = length(azurerm_dns_ns_record.delegation) == 0
    error_message = "com manage_delegation desligado não deveria haver registro no Azure"
  }

  # A zona da AWS continua sendo criada: o interruptor desliga a delegação, não a subzona.
  assert {
    condition     = aws_route53_zone.subzone.name == "nonprod.exemplo.com"
    error_message = "a subzona deveria existir mesmo sem delegação"
  }
}

# Com a delegação ligada, os valores do Azure deixam de ser opcionais. Sem isto o plan
# quebraria adiante, no provider, com mensagem que não explica o que falta.
run "delegacao_ligada_sem_subscription_e_erro" {
  command = plan

  variables {
    azure_subscription_id = null
  }

  expect_failures = [var.azure_subscription_id]
}

run "delegacao_ligada_sem_resource_group_e_erro" {
  command = plan

  variables {
    azure_dns_resource_group = null
  }

  expect_failures = [var.azure_dns_resource_group]
}

run "dominio_com_ponto_final_e_erro" {
  command = plan

  variables {
    # O nome vira parte do FQDN da subzona e do SAN do certificado wildcard adiante; um ponto
    # final aqui produz "nonprod.exemplo.com." e quebra longe da causa.
    base_domain = "exemplo.com."
  }

  expect_failures = [var.base_domain]
}

run "rotulo_de_subzona_com_ponto_e_erro" {
  command = plan

  variables {
    subzone_label = "nonprod.interno"
  }

  expect_failures = [var.subzone_label]
}
