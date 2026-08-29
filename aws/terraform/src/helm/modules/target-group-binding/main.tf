# A ligação que falta entre o que o Terraform criou na AWS e o que o Helm criou no cluster: o
# NLB e a target group são do Terraform, o Service do gateway é do chart do Istio, e este CR diz
# ao Load Balancer Controller para manter os IPs dos pods daquele Service registrados naquela
# target group.
#
# O chart é LOCAL porque não existe chart upstream para um CR só. O caminho alternativo seria
# `kubernetes_manifest`, que faz dry-run server-side no PLAN e portanto exige o CRD já
# registrado no cluster — impossível aqui, já que o CRD chega no mesmo apply, pelo release do
# próprio controller. Um chart local mantém o apply único.
resource "helm_release" "this" {
  name      = var.name
  chart     = "${path.module}/chart"
  namespace = var.namespace

  # O namespace é do módulo ingress-istio, que o cria com o rótulo de injeção. Criá-lo aqui
  # também daria duas fontes para o mesmo objeto, e a que vencesse a corrida poderia criá-lo
  # sem o rótulo.
  create_namespace = false

  wait    = true
  timeout = 300

  values = [
    yamlencode({
      targetGroupARN = var.target_group_arn
      vpcID          = var.vpc_id
      targetType     = var.target_type

      serviceRef = {
        name = var.service_name
        port = var.service_port
      }
    }),
  ]
}
