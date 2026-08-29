locals {
  chart_repository = "https://istio-release.storage.googleapis.com/charts"

  # O chart do gateway tira o prefixo `istio-` do nome do release ao montar o rótulo `istio:`
  # dos pods — release `istio-ingress` produz `istio: ingress`, e um nome sem o prefixo passa
  # intacto. Verificado renderizando o chart 1.30.4, não deduzido do `_helpers.tpl`.
  #
  # É esse valor que o `Gateway` CR usa no `selector`. Errar aqui não quebra nada visível: o
  # Gateway simplesmente não casa pod nenhum, e o sintoma é 503 num cluster onde tudo parece
  # saudável.
  gateway_selector = replace(var.gateway_release_name, "/^istio-/", "")
}

# CRDs e recursos de cluster. Primeiro dos três porque o istiod consome o que ele registra.
resource "helm_release" "base" {
  name       = "istio-base"
  repository = local.chart_repository
  chart      = "base"
  version    = var.chart_version
  namespace  = var.system_namespace

  # Quem cria istio-system é este release, uma vez só. O istiod aterrissa no namespace já
  # existente — duas fontes para o mesmo objeto seria pedir corrida.
  create_namespace = true

  wait    = true
  timeout = 600
}

# Plano de controle. Além de programar os proxies, é ele que publica o webhook de injeção — e
# o pod do gateway depende dele para existir, não só para funcionar (ver abaixo).
resource "helm_release" "istiod" {
  name             = "istiod"
  repository       = local.chart_repository
  chart            = "istiod"
  version          = var.chart_version
  namespace        = var.system_namespace
  create_namespace = false

  wait    = true
  timeout = 600

  values = compact([var.istiod_extra_values])

  depends_on = [helm_release.base]
}

# O gateway vive fora do istio-system: o plano de controle e o plano de dados têm superfícies de
# ataque e ciclos de atualização diferentes, e é o namespace do gateway que recebe tráfego.
#
# O rótulo NÃO é decoração. O chart do gateway entrega um Deployment com `image: auto`, e quem
# troca esse literal por uma imagem de verdade é o webhook de injeção do istiod. Sem o rótulo o
# pod é criado com `auto` como nome de imagem e morre em ImagePullBackOff — que não diz, em
# lugar nenhum, que a causa é um label faltando no namespace.
resource "kubernetes_namespace_v1" "gateway" {
  metadata {
    name   = var.gateway_namespace
    labels = { istio-injection = "enabled" }
  }
}

resource "helm_release" "gateway" {
  name             = var.gateway_release_name
  repository       = local.chart_repository
  chart            = "gateway"
  version          = var.chart_version
  namespace        = kubernetes_namespace_v1.gateway.metadata[0].name
  create_namespace = false

  wait    = true
  timeout = 600

  values = compact([
    yamlencode({
      # ClusterIP, nunca LoadBalancer. Quem materializa o load balancer desta célula é o
      # Terraform (`src/ingress`), e a ligação pods → target group é o TargetGroupBinding
      # (ADR 0008). Um Service type=LoadBalancer aqui pediria um segundo NLB — que o LBC desta
      # célula nem tem permissão para criar, então o sintoma seria um Service parado em
      # `<pending>` para sempre.
      #
      # As portas ficam no default do chart: 15021 (status), 80 e 443. A target group registra
      # a 80 e o health check bate na 15021; a 443 sobra sem uso porque quem termina TLS é o
      # ALB do hub, e o NLB interno repassa TCP puro.
      service = { type = "ClusterIP" }
    }),
    var.gateway_extra_values,
  ])

  # O webhook de injeção precisa estar de pé ANTES de o pod ser criado — `failurePolicy: Fail`
  # faz o próprio CREATE do pod ser recusado enquanto o istiod não responde. É por isso que o
  # istiod tem `wait = true` e esta aresta existe.
  depends_on = [helm_release.istiod]
}
