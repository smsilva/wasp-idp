# Ingress path: ALB → internal NLB → istio-ingressgateway

**Status:** Aceito

## Contexto

Com ingress centralizado pelo hub decidido (ADR 0004), falta o mecanismo concreto de tráfego
atravessar a fronteira de conta (hub → spoke) até chegar no gateway do service mesh de cada célula.

## Decisão

**Variante B**: ALB no hub → NLB interno na spoke (criado pelo Terraform, com IPs fixados via
`cidrhost()`) → pods do `istio-ingressgateway`, que roda como `ClusterIP` com `TargetGroupBinding`
apontando pra ele. Nada cruza conta em tempo de execução — só em tempo de provisionamento (o
Terraform da célula usa um provider da conta `network` para criar peças no hub, ver ADR 0007).

## Consequências

- IPs do NLB precisam ser fixados (`subnet_mapping { private_ipv4_address = cidrhost(...) }`)
  porque `aws_lb` não os expõe como output de forma confiável — sem isso o lado hub não tem valor
  estável pra apontar a target group.
- O `TargetGroupBinding` não pode levar bloco `networking`: as regras de security group (portas 80
  e 15021) já são geridas pelo Terraform, e a policy IAM da célula não tem nenhuma action de SG, de
  propósito.
- Health check do hub não consegue casar `Host` (limitação documentada do ELB) — ver a nota do
  `matcher = "200-404"` como consequência direta, registrada como item de follow-up (issue
  `private-access-ingress` "Estreitar matcher").
