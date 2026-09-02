# Valores de IDENTIDADE reais desta conta/Organization. Gitignored — o repo é público.
# Inventário e instruções: values.tfvars.example.

base_domain = "wasp.silvios.me"

azure_subscription_id    = "636a465c-d6b1-4533-b071-64cea37a2bf6"
azure_dns_resource_group = "wasp-foundation"

operator_group_ids = ["3418c4d8-f051-7051-668e-da8de656357f"]

spoke_account_ids = ["270222614208"]

network_account_id = "094289743086"

target_account_ids = ["832721568602"]

# BREAK-GLASS — endpoint público fechado. Descomente para abrir.
# endpoint_public_access = true
# public_access_cidrs    = ["203.0.113.10/32"]

# Admins do cluster (access entries). O criador (github-actions-provision) tem acesso
# automatico; os ARNs aqui sao principals ADICIONAIS com cluster-admin.
admin_principal_arns = ["arn:aws:iam::270222614208:role/OrganizationAccountAccessRole"]

# Grupos do Identity Center com admin do cluster (issue #71). Bootstrap manual concluido
# 2026-09-02: permission set + account assignment na conta cicd, role confirmada
# (AWSReservedSSO_PlatformAdmin_b62cbad9a132c25c). Ver aws/docs/bootstrap/01-identity-center-eks-admin.md.
admin_group_ids = {
  PlatformAdmin = "3418c4d8-f051-7051-668e-da8de656357f" # grupo platform-admins
}
