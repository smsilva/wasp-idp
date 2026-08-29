# O controller entra na célula com um escopo deliberadamente estreito: reconciliar
# TargetGroupBinding, e nada mais.
#
# Quem cria o NLB interno e sua target group é o Terraform, na camada control-plane
# (`src/ingress`). O que o Kubernetes não sabe fazer sozinho é manter o registro de targets
# acompanhando os pods do gateway Istio — é essa a lacuna que este chart preenche.
#
# Deixar o controller no default (IngressClass `alb` + service mutator webhook) o tornaria
# capaz de materializar load balancer próprio a partir de um Ingress ou de um
# `Service type=LoadBalancer` qualquer, reabrindo a porta que o ADR 0004 fechou ao decidir
# ingress único pelo hub. A policy da Pod Identity (control-plane/main.tf) já não concede as
# actions de criação — mas recusar aqui falha claro, e não em AccessDenied no log do pod.
resource "helm_release" "this" {
  name       = "aws-load-balancer-controller"
  repository = "https://aws.github.io/eks-charts"
  chart      = "aws-load-balancer-controller"
  version    = var.chart_version
  namespace  = var.namespace

  # kube-system já existe; pedir criação só acrescenta uma chamada que pode falhar.
  create_namespace = false

  # O CRD TargetGroupBinding é registrado por este chart, e o recurso que o consome vem
  # depois no mesmo apply. Sem `wait`, esse recurso corre contra o registro do CRD e falha
  # com "no matches for kind".
  wait    = true
  timeout = 600

  values = compact([
    yamlencode({
      # Explícitos de propósito: no default o controller resolve os três por IMDS, que
      # depende do hop limit do nó. São dados conhecidos no apply — não há razão para
      # descobrí-los em runtime.
      clusterName = var.cluster_name
      region      = var.region
      vpcId       = var.vpc_id

      # A SA é criada pelo chart; quem a liga ao role é a PodIdentityAssociation, que aponta
      # para este par (namespace, nome). Divergir aqui não quebra o apply — quebra em
      # AccessDenied no primeiro reconcile, longe da causa.
      serviceAccount = {
        create = true
        name   = var.service_account_name
      }

      # Sem IngressClass: não há Ingress ALB nesta célula, e o CRD de params não teria uso.
      createIngressClassResource = false
      ingressClassParams         = { create = false }

      # Sem o mutator webhook o controller deixa de se declarar dono de todo
      # `Service type=LoadBalancer` novo do cluster. Bônus operacional: esse webhook tem
      # failurePolicy `Fail`, então com ele ligado um controller indisponível bloquearia a
      # criação de Services em todo o cluster.
      enableServiceMutatorWebhook = false

      # Consultados pelo controller ao reconciliar, e fora da policy mínima. No default
      # (nulo) ele descobriria a ausência por tentativa e erro.
      enableShield = false
      enableWaf    = false
      enableWafv2  = false
    }),
    var.extra_values,
  ])
}
