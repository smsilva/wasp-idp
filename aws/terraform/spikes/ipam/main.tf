# SPIKE DESCARTAVEL — nao faz parte da sequencia de provisionamento. Ver README.md desta pasta.
#
# Prova o desenho de aws/docs/network/08-ipam.md ponta a ponta, no menor numero de recursos que
# ainda responde as perguntas da issue #15: de quem e o escopo, como as spokes ja alocadas entram
# sem re-enderecar, e quanto custa.
#
# Tres contas, tres providers. O DEFAULT e a `network`, porque e ela quem hospeda o IPAM: aqui o
# recurso comum e o da network, ao contrario de regions/<r>/, onde o default e a celula.

provider "aws" {
  region  = var.region
  profile = var.network_profile

  default_tags {
    tags = {
      "managed-by" = "terraform"
      "layer"      = "spike-ipam"
      "lifecycle"  = "disposable"
    }
  }
}

# So delega o IPAM admin. A management NAO pode ser o IPAM account — "You cannot use the AWS
# Organizations management account as the IPAM account" (enable-integ-ipam.html). E quem delega,
# nunca quem opera.
provider "aws" {
  alias   = "management"
  region  = var.region
  profile = var.management_profile

  default_tags {
    tags = {
      "managed-by" = "terraform"
      "layer"      = "spike-ipam"
      "lifecycle"  = "disposable"
    }
  }
}

# Conta spoke: prova que uma conta que NAO e dona do pool consegue alocar dele via RAM, sem ver nem
# alterar o plano de enderecamento.
provider "aws" {
  alias   = "spoke"
  region  = var.region
  profile = var.spoke_profile

  default_tags {
    tags = {
      "managed-by" = "terraform"
      "layer"      = "spike-ipam"
      "lifecycle"  = "disposable"
    }
  }
}

data "aws_organizations_organization" "this" {
  provider = aws.management
}

# O account id do IPAM admin vem da propria credencial da conta `network` — nunca de um literal.
data "aws_caller_identity" "network" {}

# ─── 1. Delegacao (acao ORG-WIDE) ────────────────────────────────────────────────────────────────
# Cria a service-linked role AWSServiceRoleForIPAM em TODAS as contas membro, e a partir dai o IPAM
# monitora (e cobra) todo IP ativo da Organization — nao apenas o das contas que alocam de pool.
# Fazer esta delegacao pelo console/CLI do Organizations em vez do IPAM NAO cria a SLR, e o IPAM
# fica sem monitorar nada.
resource "aws_vpc_ipam_organization_admin_account" "network" {
  provider = aws.management

  delegated_admin_account_id = data.aws_caller_identity.network.account_id

  lifecycle {
    precondition {
      condition     = data.aws_caller_identity.network.account_id != data.aws_organizations_organization.this.master_account_id
      error_message = "o IPAM admin nao pode ser a management account — a AWS recusa, e falhar aqui e mais barato que falhar na API. Conferir os profiles."
    }
  }
}

# ─── 2. O IPAM ───────────────────────────────────────────────────────────────────────────────────
# tier = advanced e OBRIGATORIO, nao escolha: pool no escopo privado nao existe no Free Tier.
# cascade = true e o que garante destroy limpo — sem ele, apagar o IPAM exige remover pools,
# alocacoes e escopos na ordem, e um destroy pela metade TRAVA o downgrade para Free.
resource "aws_vpc_ipam" "this" {
  description = "Spike da issue #15 — descartavel. Escopo privado do supernet ${var.supernet}."
  tier        = "advanced"
  cascade     = true

  dynamic "operating_regions" {
    for_each = keys(var.regional_blocks)
    content {
      region_name = operating_regions.value
    }
  }

  tags = { Name = "spike-ipam" }

  depends_on = [aws_vpc_ipam_organization_admin_account.network]
}

# ─── 3. Pool top-level: contem, nao aloca ────────────────────────────────────────────────────────
# Sem locale de proposito. Pool sem locale nao aloca para recurso e nao aceita auto_import — ele so
# segura o supernet e o subdivide.
resource "aws_vpc_ipam_pool" "supernet" {
  description    = "Top-level: supernet inteira, sem locale (contem, nao aloca)"
  address_family = "ipv4"
  ipam_scope_id  = aws_vpc_ipam.this.private_default_scope_id

  tags = { Name = "spike-supernet" }
}

resource "aws_vpc_ipam_pool_cidr" "supernet" {
  ipam_pool_id = aws_vpc_ipam_pool.supernet.id
  cidr         = var.supernet
}

# ─── 4. Pool regional: onde a politica vira mecanismo ────────────────────────────────────────────
# locale e IMUTAVEL, e e o que impede um erro de regiao virar CIDR fora do lugar. As regras de
# alocacao NAO sao herdadas do pai — "the allocation rules for the Regional pool are not inherited
# from the top-level pool" — por isso estao declaradas aqui, e nao lá.
resource "aws_vpc_ipam_pool" "regional" {
  for_each = var.regional_blocks

  description         = "Pool regional ${each.key}"
  address_family      = "ipv4"
  ipam_scope_id       = aws_vpc_ipam.this.private_default_scope_id
  source_ipam_pool_id = aws_vpc_ipam_pool.supernet.id
  locale              = each.key

  # Adota as VPCs que JA existem dentro deste bloco, sem recriar nenhuma. Indisponivel em pool sem
  # locale — e a razao de o auto_import morar no pool regional e nao no top-level.
  auto_import = true

  # Piso, teto e default do tamanho do bloco. O /16 por VPC do ADR 0003 continua sendo o default,
  # mas o pool passa a aceitar celulas menores sem que ninguem precise recalcular octeto.
  allocation_min_netmask_length     = 16
  allocation_max_netmask_length     = 28
  allocation_default_netmask_length = 16

  # A regra mais subestimada: alocar passa a EXIGIR a tag. Um apply que a esqueca nao pega um bloco
  # errado — ele falha. Ver a prova 5 no README.
  allocation_resource_tags = {
    (var.allocation_tag_key) = "spike"
  }

  tags = { Name = "spike-regional-${each.key}" }
}

resource "aws_vpc_ipam_pool_cidr" "regional" {
  for_each = var.regional_blocks

  ipam_pool_id = aws_vpc_ipam_pool.regional[each.key].id
  cidr         = each.value

  depends_on = [aws_vpc_ipam_pool_cidr.supernet]
}

# ─── 5. Reserva da Organization: alocacao EXPLICITA ──────────────────────────────────────────────
# O bloco N=0 nao tem recurso nenhum, entao o auto_import nunca o adotaria. Uma allocation explicita
# reserva o espaco ("preventing usage by IPAM") sem vincular VPC alguma — que e precisamente a
# diferenca entre este recurso e o auto_import.
resource "aws_vpc_ipam_pool_cidr_allocation" "organization_reserved" {
  count = var.organization_reserved_block == null ? 0 : 1

  ipam_pool_id = aws_vpc_ipam_pool.regional[var.region].id
  cidr         = var.organization_reserved_block
  description  = "Reservado a Organization (N=0) — sem recurso, por isso explicito"

  depends_on = [aws_vpc_ipam_pool_cidr.regional]
}

# ─── 6. RAM: alocar do pool != administrar o pool ────────────────────────────────────────────────
# O toggle org-wide de sharing (aws_ram_sharing_with_organization) ja esta ligado por dns/ — o
# pre-requisito mais chato ja estava pago antes deste spike.
resource "aws_ram_resource_share" "regional_pool" {
  name                      = "spike-ipam-regional-${var.region}"
  allow_external_principals = false

  tags = { Name = "spike-ipam-regional-${var.region}" }
}

resource "aws_ram_principal_association" "organization" {
  resource_share_arn = aws_ram_resource_share.regional_pool.arn
  principal          = data.aws_organizations_organization.this.arn
}

resource "aws_ram_resource_association" "regional_pool" {
  resource_share_arn = aws_ram_resource_share.regional_pool.arn
  resource_arn       = aws_vpc_ipam_pool.regional[var.region].arn
}

# ─── 7. A prova: uma VPC que pede TAMANHO, na conta que nao e dona do pool ───────────────────────
# Nenhum CIDR escrito aqui. Se este recurso nasce, a pergunta central da issue #15 esta respondida:
# a raiz declara so o tamanho, e a AWS devolve o bloco livre.
resource "aws_vpc" "proof" {
  provider = aws.spoke

  ipv4_ipam_pool_id   = aws_vpc_ipam_pool.regional[var.region].id
  ipv4_netmask_length = var.proof_vpc_netmask_length

  # Sem a tag exigida o apply FALHA — e a prova 5, controlada por var.proof_vpc_omit_tag. Nao
  # remover a tag no codigo "para simplificar": o flag existe para que a prova negativa seja
  # reproduzivel sem editar recurso.
  tags = merge(
    { Name = "spike-ipam-proof" },
    var.proof_vpc_omit_tag ? {} : { (var.allocation_tag_key) = "spike" },
  )

  depends_on = [
    aws_ram_resource_association.regional_pool,
    aws_ram_principal_association.organization,
    aws_vpc_ipam_pool_cidr.regional,
  ]
}
