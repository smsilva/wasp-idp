# Workload de prova da célula. Não é aplicação de verdade e não pretende ser: existe para que o
# `curl` público tenha o que responder, provando a cadeia inteira — ALB do hub → TGW → NLB
# interno → Envoy → pod.
#
# `go-httpbin` no lugar do `kennethreitz/httpbin` clássico: é mantido, multi-arquitetura e roda
# como usuário não-root. Ele escuta na 8080 (a imagem expõe essa porta e roda como 65532, então
# porta baixa exigiria capability que o pod não tem); o Service traduz para 80, que é o que o
# VirtualService roteia.
resource "kubernetes_namespace_v1" "this" {
  metadata {
    name = var.namespace

    # O workload entra na malha. Não é exigência do roteamento — o gateway alcançaria o Service
    # sem sidecar — mas é a configuração realista, e é ela que se quer exercitar aqui.
    labels = { istio-injection = "enabled" }
  }
}

resource "helm_release" "this" {
  name             = var.name
  chart            = "${path.module}/chart"
  namespace        = kubernetes_namespace_v1.this.metadata[0].name
  create_namespace = false

  wait    = true
  timeout = 300

  values = compact([
    yamlencode({
      host    = var.host
      gateway = var.gateway_ref
      image   = { tag = var.image_tag }
    }),
    var.extra_values,
  ])
}
