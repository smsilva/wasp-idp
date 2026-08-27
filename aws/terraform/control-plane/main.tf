locals {
  install_external_secrets = true
  install_argocd           = true
  install_crossplane       = true
  install_argocd_oidc      = false # exige o client secret ja no Secrets Manager
  install_app_of_apps      = false # entregue por GitOps, fora do Terraform

  # Mesmo valor de connectivity/us-east-1 — decisao irreversivel documentada, nao segredo.
  supernet = "10.0.0.0/12"

  tags = { role = "control-plane" }
}

# A VPC hub e lida pela API da AWS, nao pelo state da camada 1. A camada 2 depende do
# recurso existir, nao do arquivo de state — se a camada 1 mudar de backend ou de chave,
# isto continua valendo. Custo: exige um provider aliasado e credencial de leitura na
# conta network.
data "aws_vpc" "hub" {
  provider = aws.network

  filter {
    name   = "tag:Name"
    values = [var.hub_vpc_name]
  }
}

module "network" {
  source = "../src/network"

  name               = var.name
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
  enable_nat_gateway = var.enable_nat_gateway
  tags               = local.tags
}

# --------------------------------------------------------------------------------------
# 2.3 — attachment desta spoke no TGW da conta network. Sem isto o tunel do Client VPN
# alcanca a VPC hub e para ai.
# --------------------------------------------------------------------------------------

# O TGW pertence a conta network; lido por tag, mesmo padrao de data.aws_vpc.hub acima.
data "aws_ec2_transit_gateway" "hub" {
  provider = aws.network

  filter {
    name   = "tag:Name"
    values = ["poc-hub-tgw"]
  }
}

# O compartilhamento (RAM) e criado do lado do hub, em connectivity/, e so funciona com
# "sharing with AWS Organizations" ligado na Organization (raiz dns/, aplicado uma vez —
# nao e o TGW quem liga isto). Com ele ligado, o attachment cross-conta nasce ja associado
# sem convite — nao ha aws_ram_resource_share_accepter para rodar aqui.
#
# Quem cria o attachment e a conta dona da VPC (cicd) — provider default, nao aliasado.
resource "aws_ec2_transit_gateway_vpc_attachment" "this" {
  vpc_id             = module.network.vpc_id
  subnet_ids         = module.network.private_subnet_ids
  transit_gateway_id = data.aws_ec2_transit_gateway.hub.id

  # Mesma disciplina de connectivity/: nada por default, associacao e propagacao explicitas.
  transit_gateway_default_route_table_association = false
  transit_gateway_default_route_table_propagation = false

  tags = merge(local.tags, { Name = "${var.name}-tgw-attachment" })

  lifecycle {
    # Perpetual diff estrutural de attachment CROSS-CONTA: estes dois atributos nao existem
    # na API do attachment (sao write-only, so valem na criacao) e o provider os deriva
    # inspecionando as route tables do TGW. Elas pertencem a conta network, e este recurso e
    # lido pelo provider default (cicd), que nao as enxerga — entao o refresh devolve o
    # default `true` e o plan propoe `true -> false` para sempre, sem nunca convergir.
    #
    # A verdade sobre isolamento NAO esta aqui: esta no TGW (default association/propagation
    # desabilitados em connectivity/) e nas associacao/propagacoes explicitas abaixo.
    # Verificado na AWS: este attachment propaga SO para tgw-rt-hub, nada em default.
    ignore_changes = [
      transit_gateway_default_route_table_association,
      transit_gateway_default_route_table_propagation,
    ]
  }
}

# O TGW nasce com AutoAcceptSharedAttachments = disable (connectivity/) — RAM resolve o
# convite de COMPARTILHAMENTO, mas o attachment em si fica em pendingAcceptance ate o dono
# do TGW (conta network) aceitar explicitamente. Sao dois mecanismos distintos; sem este
# accepter, associacao/propagacao/rota falham com "is in invalid state".
resource "aws_ec2_transit_gateway_vpc_attachment_accepter" "this" {
  provider = aws.network

  transit_gateway_attachment_id = aws_ec2_transit_gateway_vpc_attachment.this.id

  # As duas metades do MESMO attachment gerenciam os mesmos atributos — sem os valores
  # explícitos aqui também, o accepter reverteria para o default `true` a cada apply e
  # brigaria com o attachment, num "perpetual diff" que nunca estabiliza.
  transit_gateway_default_route_table_association = false
  transit_gateway_default_route_table_propagation = false

  tags = merge(local.tags, { Name = "${var.name}-tgw-attachment" })
}

# tgw-rt-<spoke>: pertence a conta dona do TGW (network), mas o ciclo de vida e o desta
# spoke — por isso mora no state dela, via provider aliasado, e nao em connectivity/.
resource "aws_ec2_transit_gateway_route_table" "spoke" {
  provider = aws.network

  transit_gateway_id = data.aws_ec2_transit_gateway.hub.id

  tags = merge(local.tags, { Name = "${var.name}-tgw-rt-spoke" })
}

resource "aws_ec2_transit_gateway_route_table_association" "spoke" {
  provider = aws.network

  transit_gateway_attachment_id  = aws_ec2_transit_gateway_vpc_attachment.this.id
  transit_gateway_route_table_id = aws_ec2_transit_gateway_route_table.spoke.id

  depends_on = [aws_ec2_transit_gateway_vpc_attachment_accepter.this]
}

# tgw-rt-hub — a route table do proprio hub, ja existe em connectivity/. Lida por tag, nao
# por terraform_remote_state, mesmo padrao do resto desta camada.
data "aws_ec2_transit_gateway_route_table" "hub" {
  provider = aws.network

  filter {
    name   = "tag:Name"
    values = ["poc-hub-tgw-rt-hub"]
  }
}

# O attachment do proprio hub, tambem ja existe em connectivity/.
data "aws_ec2_transit_gateway_vpc_attachment" "hub" {
  provider = aws.network

  filter {
    name   = "tag:Name"
    values = ["poc-hub-tgw-attachment"]
  }
}

# As duas propagacoes sao o que fecha o circuito de ida e volta: sem a primeira o hub nao
# aprende a rota para esta spoke; sem a segunda esta spoke nao aprende a rota de volta para
# o hub (e, atras dela, para o cliente VPN).
resource "aws_ec2_transit_gateway_route_table_propagation" "spoke_to_hub" {
  provider = aws.network

  transit_gateway_attachment_id  = aws_ec2_transit_gateway_vpc_attachment.this.id
  transit_gateway_route_table_id = data.aws_ec2_transit_gateway_route_table.hub.id

  depends_on = [aws_ec2_transit_gateway_vpc_attachment_accepter.this]
}

resource "aws_ec2_transit_gateway_route_table_propagation" "hub_to_spoke" {
  provider = aws.network

  transit_gateway_attachment_id  = data.aws_ec2_transit_gateway_vpc_attachment.hub.id
  transit_gateway_route_table_id = aws_ec2_transit_gateway_route_table.spoke.id
}

# Rota de volta na propria VPC desta spoke: uma so, para o supernet inteiro, mesma logica de
# connectivity/ — rota e topologia, nao cresce por spoke.
#
# NAO existe rota para o client CIDR do Client VPN (100.64.0.0/22), e a ausencia e deliberada:
# o Client VPN faz SNAT. O trafego do operador chega a esta spoke com origem no CIDR da VPC
# hub (10.1.x.x), nao em 100.64.x.x — comprovado no aceite do 2.3, liberando so 10.1.0.0/16 no
# security group do cluster. O retorno cai nesta mesma rota do supernet.
#
# A doc do cenario "peered VPC" do Client VPN diz o mesmo por outro caminho: manda liberar o
# SECURITY GROUP do endpoint nos recursos de destino, nao o client CIDR. Duas rotas para
# 100.64.0.0/22 (uma aqui, outra estatica em tgw-rt-spoke) chegaram a ser escritas perseguindo
# a hipotese contraria; foram removidas depois do teste real.
resource "aws_route" "spoke_to_hub" {
  route_table_id         = module.network.private_route_table_id
  destination_cidr_block = local.supernet
  transit_gateway_id     = data.aws_ec2_transit_gateway.hub.id

  # Sem esperar o accepter, o attachment ainda está em pendingAcceptance e a AWS recusa a
  # rota com "TransitGatewayID.NotFound" — mensagem que não diz que a causa é o aceite.
  depends_on = [aws_ec2_transit_gateway_vpc_attachment.this, aws_ec2_transit_gateway_vpc_attachment_accepter.this]
}

module "cluster" {
  source = "../src/cluster"

  name                   = var.name
  kubernetes_version     = var.kubernetes_version
  subnet_ids             = module.network.control_plane_subnet_ids
  endpoint_public_access = var.endpoint_public_access
  public_access_cidrs    = var.public_access_cidrs
  access_entries         = var.access_entries
  tags                   = local.tags
}

# --------------------------------------------------------------------------------------
# 2.4 — o caminho privado ate a API. NAO e trabalho de DNS.
# --------------------------------------------------------------------------------------

# O passo nasceu no plano como "associar a private hosted zone do endpoint a VPC hub". Esse
# caminho nao existe: a zona e criada pela AWS e, na letra da doc do EKS, "is managed by
# Amazon EKS, and it doesn't appear in your account's Route 53 resources" — nao ha zona para
# ler por data source nem para autorizar associacao.
#
# E o plano B (Route 53 Resolver inbound endpoint, ~US$ 0,25/h) e desnecessario: com o
# endpoint publico desligado, "the cluster's API server endpoint is resolved by public DNS
# servers to a private IP address from the VPC". O nome resolve para IP privado no DNS que o
# operador ja usa; o que falta e so o pacote chegar.
#
# Sobra o que a doc prescreve para o caso "connected network" (TGW): "You must ensure that
# your Amazon EKS control plane security group contains rules to allow ingress traffic on
# port 443 from your connected network."
#
# A origem e o CIDR da VPC HUB, nao o client CIDR: o Client VPN faz SNAT, e o pacote do
# operador chega aqui com 10.1.x.x — comprovado com ping no 2.3. Mesmo motivo pelo qual esta
# camada nao tem rota para 100.64.0.0/22.
resource "aws_vpc_security_group_ingress_rule" "api_from_hub" {
  security_group_id = module.cluster.cluster_security_group_id
  description       = "Kubernetes API from the hub VPC (Client VPN SNATs to the hub CIDR)"

  cidr_ipv4   = data.aws_vpc.hub.cidr_block
  ip_protocol = "tcp"
  from_port   = 443
  to_port     = 443
}

module "nodegroup" {
  source = "../src/nodegroup"

  cluster_name  = module.cluster.cluster_name
  node_role_arn = module.cluster.node_role_arn
  subnet_ids    = module.network.private_subnet_ids
  tags          = local.tags
}

module "pod_identity_ebs_csi" {
  source = "../src/pod-identity"

  name                 = "${var.name}-ebs-csi"
  cluster_name         = module.cluster.cluster_name
  namespace            = "kube-system"
  service_account_name = "ebs-csi-controller-sa"
  managed_policy_arns  = ["arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"]
  tags                 = local.tags
}

module "pod_identity_eso" {
  source = "../src/pod-identity"

  name                 = "${var.name}-external-secrets"
  cluster_name         = module.cluster.cluster_name
  namespace            = "external-secrets"
  service_account_name = "external-secrets"
  policy_json = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret",
      ]
      Resource = "*"
    }]
  })
  tags = local.tags
}

# Esta e a razao de ser da camada: o Crossplane deixa de depender da access key de longa
# duracao do crossplane-poc e passa a assumir os roles das contas alvo por Pod Identity.
module "pod_identity_crossplane" {
  source = "../src/pod-identity"

  name                 = "${var.name}-crossplane"
  cluster_name         = module.cluster.cluster_name
  namespace            = "crossplane-system"
  service_account_name = "crossplane"
  policy_json = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["sts:AssumeRole", "sts:TagSession"]
      Resource = [for account_id in var.target_account_ids : "arn:aws:iam::${account_id}:role/crossplane-*"]
    }]
  })
  tags = local.tags
}

# A association de Pod Identity vem ANTES do release: se o pod subir sem ela, falha em
# AccessDenied e fica em CrashLoop ate um restart manual.
#
# E a regra de 443 vem antes de TUDO que fala com o API server: com o endpoint publico
# fechado, o provider helm alcanca o cluster pelo tunel, e sem a regra o SG do cluster recusa
# a conexao. O sintoma seria timeout no primeiro release, longe da causa. A aresta e
# explicita porque nada na configuracao do provider a cria.
module "external_secrets" {
  source = "../src/helm/modules/external-secrets"
  count  = local.install_external_secrets ? 1 : 0

  depends_on = [
    module.nodegroup,
    module.pod_identity_eso,
    aws_vpc_security_group_ingress_rule.api_from_hub,
  ]
}

module "argo_cd" {
  source = "../src/helm/modules/argo-cd"
  count  = local.install_argocd ? 1 : 0

  oidc_enabled = local.install_argocd_oidc

  depends_on = [module.external_secrets]
}

module "crossplane" {
  source = "../src/helm/modules/crossplane"
  count  = local.install_crossplane ? 1 : 0

  depends_on = [
    module.nodegroup,
    module.pod_identity_crossplane,
    aws_vpc_security_group_ingress_rule.api_from_hub,
  ]
}

# Fronteira com o GitOps. Tudo que o app-of-apps precisa saber sobre esta celula esta
# aqui — nenhum manifesto do GitOps carrega id de conta ou de VPC hardcoded.
resource "kubernetes_config_map_v1" "platform_bootstrap" {
  metadata {
    name      = "platform-bootstrap"
    namespace = "crossplane-system"
  }

  data = {
    region            = var.region
    clusterName       = module.cluster.cluster_name
    hubVpcId          = data.aws_vpc.hub.id
    spokeSubnetIds    = join(",", module.network.private_subnet_ids)
    crossplaneRoleArn = module.pod_identity_crossplane.role_arn
    networkAccountId  = var.network_account_id
    targetAccountIds  = join(",", var.target_account_ids)
  }

  depends_on = [
    module.crossplane,
    aws_vpc_security_group_ingress_rule.api_from_hub,
  ]
}
