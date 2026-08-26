# Pré-requisito de qualquer attachment cross-conta de TGW (2.3): sem "sharing with AWS
# Organizations" habilitado, a AWS recusa CreateResourceShareAssociation com
# OperationNotPermittedException. Fica aqui, não em connectivity/ (T1, destruída toda noite) —
# é configuração PERMANENTE da Organization inteira, não do ciclo de vida do TGW.

mock_provider "aws" {}

mock_provider "aws" {
  alias = "management"
}

mock_provider "azurerm" {}

variables {
  base_domain              = "exemplo.com"
  azure_subscription_id    = "00000000-0000-0000-0000-000000000000"
  azure_dns_resource_group = "rg-dns"
}

# O recurso não tem argumento nenhum além de id (computado) — a própria existência dele no
# plan é o "ligado". Não há atributo para comparar valor.
run "o_ram_sharing_com_a_organization_e_declarado" {
  command = plan

  # id só existe depois do apply; o override dá um valor conhecido no plan.
  override_resource {
    target          = aws_ram_sharing_with_organization.this
    override_during = plan
    values = {
      id = "management-account-id"
    }
  }

  assert {
    condition     = aws_ram_sharing_with_organization.this.id == "management-account-id"
    error_message = "aws_ram_sharing_with_organization.this deveria existir no plan"
  }
}
