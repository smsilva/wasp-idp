locals {
  install_load_balancer_controller = true
  install_ingress_istio            = true
  install_external_secrets         = true

  # Derivado, nunca escrito à mão: o binding precisa do CRD que o LBC registra E do Service que
  # o Istio cria. Ligá-lo com um dos dois desligados falharia no apply — e o `one()` que lê os
  # outputs do ingress_istio devolveria null antes disso, com erro que não explica a causa.
  install_target_group_binding = local.install_load_balancer_controller && local.install_ingress_istio

  # O workload de prova depende da rota, que é do Gateway CR do ingress_istio.
  install_httpbin = local.install_ingress_istio

  install_argocd      = true
  install_crossplane  = true
  install_argocd_oidc = false # exige o client secret ja no Secrets Manager
  install_app_of_apps = false # entregue por GitOps, fora do Terraform

  # Mesmo valor do hub, em qualquer regiao — decisao irreversivel documentada, nao segredo.
  supernet = "10.0.0.0/12"

  # A subzona que a camada 02 delegou, e o wildcard DESTA celula dentro dela. Wildcard cobre um
  # nivel so (`*.*.` nao existe), e e exatamente por isso que ha um certificado por celula em
  # vez de um unico na subzona: `*.nonprod.<dominio>` nao casa `app.<celula>.nonprod.<dominio>`.
  subzone_fqdn  = "${var.subzone_label}.${var.base_domain}"
  cell_wildcard = "*.${var.name}.${local.subzone_fqdn}"

  # O host de entrada DESTA celula, dentro do wildcard acima. `services.`, nunca `app.`:
  # qualquer outro nome sob o wildcard cai no fixed-response 404 do listener do ALB, e o
  # sintoma e indistinguivel de rota faltando no cluster.
  cell_services_fqdn = "services.${var.name}.${local.subzone_fqdn}"

  # Priority da listener rule: unico por listener, e o listener e COMPARTILHADO entre celulas.
  # Derivado de algo estavel da celula (o nome), nunca de count.index — que mudaria se a ordem
  # das celulas mudasse, reescrevendo rules alheias. Faixa valida do ALB: 1..50000.
  #
  # Colisao entre duas celulas e possivel (e o preco de derivar em vez de coordenar). Ela falha
  # ALTO no apply, com erro de priority duplicada — o que e aceitavel; o inaceitavel seria
  # sobrescrever a rule de outra celula em silencio.
  listener_rule_priority = 1 + parseint(substr(sha256(var.name), 0, 4), 16) % 50000

  tags = { role = "control-plane" }
}

module "network" {
  source = "../network"

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

# O compartilhamento (RAM) e criado do lado do hub, em connectivity/, e so funciona com
# "sharing with AWS Organizations" ligado na Organization (raiz dns/, aplicado uma vez —
# nao e o TGW quem liga isto). Com ele ligado, o attachment cross-conta nasce ja associado
# sem convite — nao ha aws_ram_resource_share_accepter para rodar aqui.
#
# Quem cria o attachment e a conta dona da VPC (cicd) — provider default, nao aliasado.
#
# ORDEM CONTRA O ENDPOINT PRIVADO — uma aresta só, nas duas direções.
#
# O caminho de rede desta spoke até o API server (attachment + accepter + associação +
# propagações + rota) tem de existir ANTES de qualquer recurso dos providers kubernetes/helm,
# e tem de sobreviver ATÉ o último deles ser destruído. Nada na configuração daqueles
# providers cria essa aresta sozinho.
#
# São a mesma aresta: `depends_on` é uma só relação, e o destroy percorre o grafo ao
# contrário. Os quatro consumidores da API (o ConfigMap e os três módulos de helm) declaram
# depends_on nestes recursos de rede — logo o apply cria a rede primeiro e o destroy apaga os
# consumidores primeiro. Não existe "aresta simétrica na direção contrária" a acrescentar.
#
# Foi essa a lição de 2026-08-28: a tentativa de escrever a segunda direção pôs
# `depends_on` nos consumidores DENTRO dos recursos de rede, invertendo a aresta de apply. O
# resultado foi um deadlock — o helm tentou alcançar o API server antes de o attachment
# existir e morreu com `dial tcp <ip-privado>:443: i/o timeout`, o MESMO sintoma do incidente
# de destroy de 2026-08-27 que a mudança pretendia corrigir. 49 de 61 recursos aplicados, e a
# rede toda de fora do state.
resource "aws_ec2_transit_gateway_vpc_attachment" "this" {
  vpc_id             = module.network.vpc_id
  subnet_ids         = module.network.private_subnet_ids
  transit_gateway_id = var.transit_gateway_id

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

  transit_gateway_id = var.transit_gateway_id

  tags = merge(local.tags, { Name = "${var.name}-tgw-rt-spoke" })
}

resource "aws_ec2_transit_gateway_route_table_association" "spoke" {
  provider = aws.network

  transit_gateway_attachment_id  = aws_ec2_transit_gateway_vpc_attachment.this.id
  transit_gateway_route_table_id = aws_ec2_transit_gateway_route_table.spoke.id

  depends_on = [aws_ec2_transit_gateway_vpc_attachment_accepter.this]
}

# As duas propagacoes sao o que fecha o circuito de ida e volta: sem a primeira o hub nao
# aprende a rota para esta spoke; sem a segunda esta spoke nao aprende a rota de volta para
# o hub (e, atras dela, para o cliente VPN).
resource "aws_ec2_transit_gateway_route_table_propagation" "spoke_to_hub" {
  provider = aws.network

  transit_gateway_attachment_id  = aws_ec2_transit_gateway_vpc_attachment.this.id
  transit_gateway_route_table_id = var.hub_transit_gateway_route_table_id

  depends_on = [aws_ec2_transit_gateway_vpc_attachment_accepter.this]
}

resource "aws_ec2_transit_gateway_route_table_propagation" "hub_to_spoke" {
  provider = aws.network

  transit_gateway_attachment_id  = var.hub_transit_gateway_attachment_id
  transit_gateway_route_table_id = aws_ec2_transit_gateway_route_table.spoke.id

  # Referencia so um data source (o attachment do HUB, gerenciado em connectivity/) e a
  # route table desta spoke — sem aresta propria com o attachment/accepter desta camada, essa
  # propagacao nao tinha NENHUMA ordem garantida em relacao ao resto do destroy. Foi o que
  # cortou a rota primeiro no incidente de 2026-08-27 (ver comentario acima do attachment).
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
  transit_gateway_id     = var.transit_gateway_id

  # Sem esperar o accepter, o attachment ainda está em pendingAcceptance e a AWS recusa a
  # rota com "TransitGatewayID.NotFound" — mensagem que não diz que a causa é o aceite.
  #
  # Esta é a rota mais provável de ter sido a causa direta do incidente de 2026-08-27: sua
  # destruição é quase instantânea (ao contrário do attachment, que leva minutos), então sem
  # ordem garantida ela corta o caminho para o endpoint privado antes de qualquer coisa
  # perceber. A ordem vem do `depends_on` que os consumidores da API declaram NESTA rota —
  # não do contrário. Ver o comentário do attachment.
  depends_on = [
    aws_ec2_transit_gateway_vpc_attachment.this,
    aws_ec2_transit_gateway_vpc_attachment_accepter.this,
  ]
}

# A MESMA rota, na tabela das públicas. Não é redundância: `module.cluster` recebe
# `control_plane_subnet_ids` (as 4 subnets), e a AWS escolhe livremente onde põe as ENIs do
# endpoint privado. No apply de 2026-08-28 elas caíram nas duas PÚBLICAS (10.2.9.250 e
# 10.2.31.21) — o pacote do hub chegava pelo TGW, mas o retorno seguia o default da tabela
# pública, o IGW, e os dois helm_release morreram com `i/o timeout` contra o API server. Os
# applies anteriores passaram por sorte, com as ENIs nas privadas.
#
# Alcance da malha é propriedade da SPOKE, não de uma subnet dela: enquanto o cluster
# consumir as 4, a rota existe nas duas tabelas ou a reachability é sorteada a cada apply.
resource "aws_route" "spoke_to_hub_public" {
  route_table_id         = module.network.public_route_table_id
  destination_cidr_block = local.supernet
  transit_gateway_id     = var.transit_gateway_id

  depends_on = [
    aws_ec2_transit_gateway_vpc_attachment.this,
    aws_ec2_transit_gateway_vpc_attachment_accepter.this,
  ]
}

module "cluster" {
  source = "../cluster"

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

  cidr_ipv4   = var.hub_vpc_cidr_block
  ip_protocol = "tcp"
  from_port   = 443
  to_port     = 443
}

# --------------------------------------------------------------------------------------
# 3.1 — ingress da spoke. NLB interno com enderecos fixos + target group vazia; quem
# registra os pods do gateway Istio e o TargetGroupBinding do LBC, do lado do GitOps.
# --------------------------------------------------------------------------------------

module "ingress" {
  source = "../ingress"

  name                 = var.name
  vpc_id               = module.network.vpc_id
  private_subnet_ids   = module.network.private_subnet_ids
  private_subnet_cidrs = module.network.private_subnet_cidrs

  # Quem alcanca o NLB e o hub, e so ele: a decisao de ingress unico diz que nenhuma spoke
  # expoe acesso a si direto. O CIDR vem do data source da VPC hub, o mesmo que autoriza a
  # regra de 443 na API — nao ha valor de rede escrito a mao nesta camada.
  allowed_ingress_cidrs = [var.hub_vpc_cidr_block]

  tags = local.tags
}

# O caminho NLB -> pods do gateway. Fica no Terraform, e nao no networking.ingress do
# TargetGroupBinding, por dois motivos: a policy minima do LBC para quem so usa
# TargetGroupBinding (a que a doc upstream publica) NAO inclui gerencia de security group, e
# manter a regra aqui a deixa em codigo revisavel em vez de mutacao de SG em runtime.
#
# A origem e o SG do NLB, nao um CIDR: com target_type = ip a preservacao de client IP nasce
# DESLIGADA (doc do ELB: default disabled para target group de tipo IP com protocolo TCP),
# entao o pacote chega ao pod com origem no no do NLB — que carrega este SG.
resource "aws_vpc_security_group_ingress_rule" "gateway_from_nlb" {
  security_group_id = module.cluster.cluster_security_group_id
  description       = "Ingress gateway traffic from the internal NLB"

  referenced_security_group_id = module.ingress.security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 80
  to_port                      = 80
}

# Sem esta, o health check nunca responde e a target group fica unhealthy para sempre — com o
# gateway funcionando. O sintoma (hub reportando a spoke inteira fora) nao aponta para cá.
resource "aws_vpc_security_group_ingress_rule" "gateway_health_check_from_nlb" {
  security_group_id = module.cluster.cluster_security_group_id
  description       = "Ingress gateway status port for the NLB health check"

  referenced_security_group_id = module.ingress.security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 15021
  to_port                      = 15021
}

# 4a Pod Identity: o LBC. O CHART nao e desta camada — vem por GitOps, junto do gateway e do
# TargetGroupBinding (decisions.md §7: o Terraform entrega rede + cluster + ArgoCD +
# Crossplane "e para ai"). O que so o Terraform pode entregar e o role IAM.
#
# A policy e o conjunto MINIMO que a doc do LBC publica para quem usa apenas
# TargetGroupBinding e nao deixa o controller gerenciar security group. Ingress e Service
# type=LoadBalancer ficam de fora de proposito: o NLB e do Terraform, e um LBC capaz de criar
# load balancer proprio reabriria a porta que a decisao de ingress unico fechou.
module "pod_identity_lbc" {
  source = "../pod-identity"

  name                 = "${var.name}-load-balancer-controller"
  cluster_name         = module.cluster.cluster_name
  namespace            = "kube-system"
  service_account_name = "aws-load-balancer-controller"
  policy_json = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # Leitura de inventario: estas actions nao aceitam escopo por recurso — Describe de EC2 e
      # de ELB responde sobre a conta, nao sobre um ARN.
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeVpcs",
          "ec2:DescribeSecurityGroups",
          "ec2:DescribeInstances",
          "elasticloadbalancing:DescribeTargetGroups",
          "elasticloadbalancing:DescribeTargetHealth",
        ]
        Resource = "*"
      },
      # As que MUDAM estado aceitam ARN de target group, e aqui da para usar isso porque a
      # target group e criada pelo Terraform, nesta mesma camada: o ARN e conhecido. A policy
      # upstream do LBC usa condition por tag em vez de ARN porque lá o controller cria as
      # target groups que gerencia e nao poderia saber os ARNs de antemao — o nosso caso e
      # estritamente mais fechado. Consequencia: se um dia o LBC passar a criar target group
      # (Ingress/Service tipo LoadBalancer, nao TargetGroupBinding), esta policy precisa de
      # outra statement, e o sintoma sera AccessDenied no log do controller.
      {
        Effect = "Allow"
        Action = [
          "elasticloadbalancing:ModifyTargetGroup",
          "elasticloadbalancing:ModifyTargetGroupAttributes",
          "elasticloadbalancing:RegisterTargets",
          "elasticloadbalancing:DeregisterTargets",
        ]
        Resource = module.ingress.target_group_arn
      },
    ]
  })
  tags = local.tags
}

module "nodegroup" {
  source = "../nodegroup"

  cluster_name  = module.cluster.cluster_name
  node_role_arn = module.cluster.node_role_arn
  subnet_ids    = module.network.private_subnet_ids
  tags          = local.tags
}

module "pod_identity_ebs_csi" {
  source = "../pod-identity"

  name                 = "${var.name}-ebs-csi"
  cluster_name         = module.cluster.cluster_name
  namespace            = "kube-system"
  service_account_name = "ebs-csi-controller-sa"
  managed_policy_arns  = ["arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"]
  tags                 = local.tags
}

# Este addon mora AQUI, e nao no src/cluster junto do eks-pod-identity-agent, por causa de uma
# race que ja custou um apply inteiro (run 33505550033, 01/09/2026): o addon comecou a criar 7s
# ANTES de a association do pod_identity_ebs_csi existir. Os env vars de Pod Identity
# (AWS_CONTAINER_CREDENTIALS_FULL_URI + o volume do token) sao injetados por um webhook na
# ADMISSAO do pod, uma unica vez; pod spec e imutavel, entao os pods do ebs-csi-controller que
# nasceram naquela janela nunca recuperaram — CrashLoopBackOff permanente e addon DEGRADED pelos
# 20 min inteiros do timeout, mesmo com os nos Ready desde os 3min. Nao e falta de tempo, e falta
# de ordem: aumentar timeouts.create so adia a falha.
#
# O depends_on nao poderia ficar no src/cluster — module.pod_identity_ebs_csi le
# module.cluster.cluster_name, entao o cluster nao pode depender dele (ciclo) — e os dois addons
# compartilhavam um for_each, que nao ordena um em relacao ao outro. Mesmo split que o chart do
# Crossplane ja fez nas fases 65 -> 68 (ver aws/CLAUDE.md).
#
# O nodegroup entra no depends_on porque sem no nao ha onde admitir o controller: o addon ficaria
# Pending ate o timeout por outro motivo.
#
# Sem serviceAccountRoleArn: a identidade chega por Pod Identity. Sem addon_version: a AWS
# escolhe a compativel com a versao do cluster.
resource "aws_eks_addon" "ebs_csi" {
  cluster_name                = module.cluster.cluster_name
  addon_name                  = "aws-ebs-csi-driver"
  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"

  tags = merge(local.tags, { Name = "${var.name}-aws-ebs-csi-driver" })

  depends_on = [
    module.pod_identity_ebs_csi,
    module.nodegroup,
  ]
}

module "pod_identity_eso" {
  source = "../pod-identity"

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
  source = "../pod-identity"

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

# Primeiro chart da célula, e o único que o restante do ingress não pode dispensar: é ele que
# registra o CRD TargetGroupBinding e mantém os pods do gateway registrados na target group
# que `module.ingress` criou. Até 2026-08-28 este release era instalado à mão, por `helm`, a
# partir de um checkout local — a célula subia, mas não se reproduzia.
#
# A lista de depends_on é a mesma dos outros consumidores da API (ver o comentário em
# module.crossplane): a Pod Identity antes do release, a regra de 443 antes de qualquer
# conversa com o API server, e o caminho de rede até o endpoint privado nas duas direções.
module "aws_load_balancer_controller" {
  source = "../helm/modules/aws-load-balancer-controller"
  count  = local.install_load_balancer_controller ? 1 : 0

  cluster_name = module.cluster.cluster_name
  region       = var.region
  vpc_id       = module.network.vpc_id

  depends_on = [
    module.nodegroup,
    module.pod_identity_lbc,
    aws_vpc_security_group_ingress_rule.api_from_hub,

    module.network,
    aws_ec2_transit_gateway_vpc_attachment.this,
    aws_ec2_transit_gateway_vpc_attachment_accepter.this,
    aws_ec2_transit_gateway_route_table_association.spoke,
    aws_ec2_transit_gateway_route_table_propagation.spoke_to_hub,
    aws_ec2_transit_gateway_route_table_propagation.hub_to_spoke,
    aws_route.spoke_to_hub,
    aws_route.spoke_to_hub_public,
  ]
}

# Plano de dados do ingress: base + istiod + gateway, os três na mesma versão. O Service do
# gateway nasce ClusterIP — quem materializa o load balancer é `module.ingress`, e a ligação
# pods → target group será o TargetGroupBinding.
#
# Não depende do LBC: o gateway é um Deployment e um Service comuns, e sobe sem nada da AWS.
# Quem vai precisar do CRD que o LBC registra é o passo seguinte, não este.
#
# A aresta de rede vem explícita pelo mesmo motivo do LBC — herdar de `module.external_secrets`
# por transitividade a perderia se aquele módulo fosse desligado pelo `count`.
module "ingress_istio" {
  source = "../helm/modules/ingress-istio"
  count  = local.install_ingress_istio ? 1 : 0

  # O mesmo wildcard do certificado do ACM e do registro Route 53 desta célula. As três pontas
  # têm de concordar: o ALB só aceita a conexão para um nome coberto pelo certificado, e o
  # Envoy só roteia um host que o Gateway declara. Derivar do mesmo local é o que garante isso.
  gateway_hosts = [local.cell_wildcard]

  depends_on = [
    module.nodegroup,
    aws_vpc_security_group_ingress_rule.api_from_hub,

    module.network,
    aws_ec2_transit_gateway_vpc_attachment.this,
    aws_ec2_transit_gateway_vpc_attachment_accepter.this,
    aws_ec2_transit_gateway_route_table_association.spoke,
    aws_ec2_transit_gateway_route_table_propagation.spoke_to_hub,
    aws_ec2_transit_gateway_route_table_propagation.hub_to_spoke,
    aws_route.spoke_to_hub,
    aws_route.spoke_to_hub_public,
  ]
}

# A costura entre as duas metades da célula: o NLB e a target group são do Terraform, o Service
# do gateway é do chart do Istio, e este CR manda o Load Balancer Controller manter os IPs dos
# pods daquele Service registrados naquela target group.
#
# É o único recurso desta camada que depende dos DOIS releases anteriores por motivos
# diferentes: do LBC porque é ele que registra o CRD `TargetGroupBinding` (daí o `wait` de lá
# não ser hábito copiado), e do Istio porque `serviceRef` aponta para um Service que precisa
# existir.
#
# O ARN chega por referência, nunca colado: a target group usa `name_prefix` +
# `create_before_destroy`, então trocar a porta ou o target_type a RECRIA com outro ARN. Um
# values file colado à mão fica velho no primeiro replace, e o sintoma é uma target group vazia
# com tudo aparentemente saudável.
module "target_group_binding" {
  source = "../helm/modules/target-group-binding"
  count  = local.install_target_group_binding ? 1 : 0

  namespace        = one(module.ingress_istio[*].gateway_namespace)
  service_name     = one(module.ingress_istio[*].gateway_service_name)
  target_group_arn = module.ingress.target_group_arn
  vpc_id           = module.network.vpc_id

  # A aresta de rede até o endpoint privado chega por TRANSITIVIDADE, e aqui isso é seguro: este
  # módulo só existe quando `install_ingress_istio` é true (ver o local derivado acima), e é
  # `module.ingress_istio` que a declara. Não é o caso dos módulos atrás de um `count`
  # independente, onde repetir a lista é o que impede a aresta de sumir.
  depends_on = [
    module.aws_load_balancer_controller,
    module.ingress_istio,
  ]
}

# Workload de prova. É o que dá ao `curl` público algo para responder — sem ele o Envoy sobe
# sem rota e devolve 404 em tudo, o que se lê como falha de ingress.
#
# O host é `services.`, não `app.`: qualquer outro nome sob o wildcard cai no `fixed-response`
# 404 do listener do ALB, e o sintoma é indistinguível de rota faltando no cluster.
module "httpbin" {
  source = "../helm/modules/httpbin"
  count  = local.install_httpbin ? 1 : 0

  host        = local.cell_services_fqdn
  gateway_ref = one(module.ingress_istio[*].gateway_ref)

  # Do Gateway CR (que é do ingress_istio) porque é ele que a rota referencia; do binding
  # porque sem targets registrados a prova não fecha, e é ele quem os registra.
  depends_on = [
    module.ingress_istio,
    module.target_group_binding,
  ]
}

# A association de Pod Identity vem ANTES do release: se o pod subir sem ela, falha em
# AccessDenied e fica em CrashLoop ate um restart manual.
#
# E a regra de 443 vem antes de TUDO que fala com o API server: com o endpoint publico
# fechado, o provider helm alcanca o cluster pelo tunel, e sem a regra o SG do cluster recusa
# a conexao. O sintoma seria timeout no primeiro release, longe da causa. A aresta e
# explicita porque nada na configuracao do provider a cria.
module "external_secrets" {
  source = "../helm/modules/external-secrets"
  count  = local.install_external_secrets ? 1 : 0

  depends_on = [
    module.nodegroup,
    module.pod_identity_eso,
    aws_vpc_security_group_ingress_rule.api_from_hub,

    # O caminho de rede até o endpoint privado, nas duas direções: o apply espera a rede, e o
    # destroy (que percorre o grafo ao contrário) apaga este consumidor antes de cortá-la.
    #
    # module.network inteiro, e não só a rota: no destroy de 2026-08-28 os
    # aws_route_table_association.private foram apagados ANTES deste consumidor, e desassociar a
    # route table das subnets privadas corta o caminho até as ENIs do endpoint tão bem quanto
    # apagar a rota. A associação é recurso separado e não tem aresta com aws_route.spoke_to_hub,
    # então enumerar os seis recursos do TGW deixava esse buraco. Depender do módulo cobre
    # subnets, route tables e associações de uma vez, e não precisa ser revisitado quando o
    # módulo ganhar recurso novo.
    module.network,
    aws_ec2_transit_gateway_vpc_attachment.this,
    aws_ec2_transit_gateway_vpc_attachment_accepter.this,
    aws_ec2_transit_gateway_route_table_association.spoke,
    aws_ec2_transit_gateway_route_table_propagation.spoke_to_hub,
    aws_ec2_transit_gateway_route_table_propagation.hub_to_spoke,
    aws_route.spoke_to_hub,
    aws_route.spoke_to_hub_public,
  ]
}

module "argo_cd" {
  source = "../helm/modules/argo-cd"
  count  = local.install_argocd ? 1 : 0

  oidc_enabled = local.install_argocd_oidc

  # O caminho de rede até o endpoint privado chega aqui por TRANSITIVIDADE: external_secrets já
  # o declara, e `depends_on` é transitivo nas duas direções do grafo. Repetir a lista aqui não
  # acrescentaria ordem — só mais um lugar para esquecer de atualizar.
  depends_on = [module.external_secrets]
}

module "crossplane" {
  source = "../helm/modules/crossplane"
  count  = local.install_crossplane ? 1 : 0

  depends_on = [
    module.nodegroup,
    module.pod_identity_crossplane,
    aws_vpc_security_group_ingress_rule.api_from_hub,

    # O caminho de rede até o endpoint privado, nas duas direções: o apply espera a rede, e o
    # destroy (que percorre o grafo ao contrário) apaga este consumidor antes de cortá-la.
    #
    # module.network inteiro, e não só a rota: no destroy de 2026-08-28 os
    # aws_route_table_association.private foram apagados ANTES deste consumidor, e desassociar a
    # route table das subnets privadas corta o caminho até as ENIs do endpoint tão bem quanto
    # apagar a rota. A associação é recurso separado e não tem aresta com aws_route.spoke_to_hub,
    # então enumerar os seis recursos do TGW deixava esse buraco. Depender do módulo cobre
    # subnets, route tables e associações de uma vez, e não precisa ser revisitado quando o
    # módulo ganhar recurso novo.
    module.network,
    aws_ec2_transit_gateway_vpc_attachment.this,
    aws_ec2_transit_gateway_vpc_attachment_accepter.this,
    aws_ec2_transit_gateway_route_table_association.spoke,
    aws_ec2_transit_gateway_route_table_propagation.spoke_to_hub,
    aws_ec2_transit_gateway_route_table_propagation.hub_to_spoke,
    aws_route.spoke_to_hub,
    aws_route.spoke_to_hub_public,
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
    hubVpcId          = var.hub_vpc_id
    spokeSubnetIds    = join(",", module.network.private_subnet_ids)
    crossplaneRoleArn = module.pod_identity_crossplane.role_arn
    networkAccountId  = var.network_account_id
    targetAccountIds  = join(",", var.target_account_ids)

    # 3.1 — o que o lado GitOps precisa para ligar os pods do gateway ao NLB. E o ARN da
    # TARGET GROUP, nao o do NLB: e ele que o TargetGroupBinding consome. Passar o do load
    # balancer daria um binding que reconcilia para sempre sem registrar nada.
    ingressTargetGroupArn = module.ingress.target_group_arn

    # O role que o chart do LBC anota na service account aws-load-balancer-controller.
    loadBalancerControllerRoleArn = module.pod_identity_lbc.role_arn
  }

  depends_on = [
    module.crossplane,
    aws_vpc_security_group_ingress_rule.api_from_hub,

    # O caminho de rede até o endpoint privado, nas duas direções: o apply espera a rede, e o
    # destroy (que percorre o grafo ao contrário) apaga este consumidor antes de cortá-la.
    #
    # module.network inteiro, e não só a rota: no destroy de 2026-08-28 os
    # aws_route_table_association.private foram apagados ANTES deste consumidor, e desassociar a
    # route table das subnets privadas corta o caminho até as ENIs do endpoint tão bem quanto
    # apagar a rota. A associação é recurso separado e não tem aresta com aws_route.spoke_to_hub,
    # então enumerar os seis recursos do TGW deixava esse buraco. Depender do módulo cobre
    # subnets, route tables e associações de uma vez, e não precisa ser revisitado quando o
    # módulo ganhar recurso novo.
    module.network,
    aws_ec2_transit_gateway_vpc_attachment.this,
    aws_ec2_transit_gateway_vpc_attachment_accepter.this,
    aws_ec2_transit_gateway_route_table_association.spoke,
    aws_ec2_transit_gateway_route_table_propagation.spoke_to_hub,
    aws_ec2_transit_gateway_route_table_propagation.hub_to_spoke,
    aws_route.spoke_to_hub,
    aws_route.spoke_to_hub_public,
  ]
}

# --------------------------------------------------------------------------------------
# 3.2 — o lado HUB do ingress desta celula, na conta network
# --------------------------------------------------------------------------------------
#
# Fronteira de state segue o ciclo de vida, nao a conta: os recursos abaixo pertencem a conta
# network, mas o ciclo de vida deles e o DESTA celula — destruir a celula leva os quatro junto,
# sem orfao do lado do hub. Dai o provider aliasado, e nao connectivity/.
#
# O ALB e o listener :443 NAO nascem aqui: sao permanentes, da camada 03. Um listener por hub,
# N certificados por SNI, uma rule por celula. Chegam por referencia (var.hub_alb_listener_arn),
# mesmo padrao da VPC hub e do TGW: o consumidor declara a dependencia como aresta do grafo,
# nao redescobre por data source o que a raiz ja resolveu via output de src/hub.

data "aws_route53_zone" "subzone" {
  provider = aws.network

  name         = local.subzone_fqdn
  private_zone = false
}

# Certificado publico do ACM, validado por DNS na subzona. Nenhuma chave privada em state nem
# em disco, e rotacao automatica que o ALB acompanha.
resource "aws_acm_certificate" "cell" {
  provider = aws.network

  domain_name       = local.cell_wildcard
  validation_method = "DNS"

  # `*` NAO e caractere valido em valor de tag do ACM — o servico exige
  # `([\p{L}\p{Z}\p{N}_.:/=+\-@]*)`, mais restrito que a tag comum de EC2, e recusa o apply com
  # ValidationException apontando um indice de tag (`tags.1.member.value`) em vez do nome. Mesmo
  # tropeco do certificado default do ALB, na camada 03.
  tags = merge(local.tags, { Name = "wildcard.${var.name}.${local.subzone_fqdn}" })

  lifecycle {
    create_before_destroy = true
  }
}

# UM registro, indexado — mesma razao do certificado do Client VPN na camada 03: as chaves de um
# for_each sobre domain_validation_options viriam de atributo computado. Um dominio, nenhum SAN,
# um elemento.
resource "aws_route53_record" "cell_validation" {
  provider = aws.network

  zone_id = data.aws_route53_zone.subzone.zone_id
  name    = tolist(aws_acm_certificate.cell.domain_validation_options)[0].resource_record_name
  type    = tolist(aws_acm_certificate.cell.domain_validation_options)[0].resource_record_type
  records = [tolist(aws_acm_certificate.cell.domain_validation_options)[0].resource_record_value]

  ttl             = 60
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "cell" {
  provider = aws.network

  certificate_arn         = aws_acm_certificate.cell.arn
  validation_record_fqdns = [aws_route53_record.cell_validation.fqdn]
}

# O SNI: e isto que permite N celulas num listener :443 so. O certificate_arn vem do
# VALIDATION, nao do certificate — so ele espera a validacao terminar. Os dois ARNs sao o mesmo
# valor, entao nenhum teste offline distingue as duas referencias; o sintoma de errar e
# certificado PENDING_VALIDATION anexado ao listener.
resource "aws_lb_listener_certificate" "cell" {
  provider = aws.network

  listener_arn    = var.hub_alb_listener_arn
  certificate_arn = aws_acm_certificate_validation.cell.certificate_arn
}

# A target group vive na VPC HUB (e la que esta o ALB) e aponta para IPs da VPC da SPOKE,
# alcancaveis pelo TGW. Registrar IP fora da VPC do load balancer e suportado para faixas
# RFC 1918 roteaveis — e o caso.
#
# name_prefix, nunca name: trocar porta ou target_type forca replace, e com nome fixo nao ha
# saida (sem create_before_destroy a AWS recusa apagar porque o listener ainda aponta; com CBD
# e nome fixo recusa criar a nova, porque ja existe). Preco: 6 caracteres, entao o nome legivel
# vive na tag Name e quem consome usa o ARN.
resource "aws_lb_target_group" "hub_to_cell" {
  provider = aws.network

  name_prefix = "cell-"
  port        = 80
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.hub_vpc_id

  health_check {
    path     = "/"
    port     = "traffic-port"
    protocol = "HTTP"

    # 200-404 e escolha CONSCIENTE e provisoria. O health check chega ao Envoy do gateway com
    # Host = IP do no do ALB, que nao casa nenhum VirtualService, e o Istio responde 404 — com
    # o matcher default (200) TODOS os targets ficariam unhealthy sem nada estar errado.
    #
    # O preco: aceita como saudavel um gateway realmente quebrado, porque 404 e exatamente o
    # que um Envoy sem configuracao devolve. Estreitar para 200 exige uma rota de health no
    # Gateway/VirtualService casando QUALQUER host, que e manifesto de GitOps, nao Terraform.
    # Nao ha porta de status alcancavel daqui: a 15021 e do gateway dentro da spoke, e o
    # listener do NLB so escuta 80.
    matcher = "200-404"
  }

  tags = merge(local.tags, { Name = "${var.name}-hub-ingress" })

  lifecycle {
    create_before_destroy = true
  }
}

# Os enderecos FIXOS do NLB da spoke, um por AZ. Conhecidos em tempo de plan porque sao
# calculados (cidrhost sobre os CIDRs das privadas), nao lidos do recurso — foi para isso que
# foram fixados, e e o que permite planejar o lado hub sem o NLB existir.
resource "aws_lb_target_group_attachment" "hub_to_cell" {
  for_each = toset(module.ingress.private_ips)

  provider = aws.network

  target_group_arn = aws_lb_target_group.hub_to_cell.arn
  target_id        = each.value
  port             = 80

  # Obrigatorio para IP FORA da VPC do load balancer: o NLB esta na VPC da spoke, o ALB na VPC
  # hub. Omitir da erro que nao explica a causa.
  availability_zone = "all"
}

resource "aws_lb_listener_rule" "cell" {
  provider = aws.network

  listener_arn = var.hub_alb_listener_arn
  priority     = local.listener_rule_priority

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.hub_to_cell.arn
  }

  condition {
    host_header {
      values = [local.cell_wildcard]
    }
  }

  tags = merge(local.tags, { Name = "${var.name}-hub-ingress" })
}

# Um registro wildcard por celula, casando o wildcard do certificado: evita um registro por
# aplicacao. dns_name e zone_id vem do MESMO data source — um alias com a zone_id de outro load
# balancer e aceito pelo Route53 e nunca resolve.
resource "aws_route53_record" "cell_wildcard" {
  provider = aws.network

  zone_id = data.aws_route53_zone.subzone.zone_id
  name    = "*.${var.name}"
  type    = "A"

  alias {
    name                   = var.hub_alb_dns_name
    zone_id                = var.hub_alb_zone_id
    evaluate_target_health = false
  }
}
