output "cluster_name" {
  description = "Nome do cluster da celula."
  value       = module.cluster.cluster_name
}

# --------------------------------------------------------------------------------------
# Com o cluster dentro deste modulo, os providers kubernetes e helm da raiz nao alcancam
# mais um submodulo aninhado — os dois valores tem de atravessar como output, senao a raiz
# nao compila os providers.
# --------------------------------------------------------------------------------------

output "cluster_endpoint" {
  description = "Endpoint da API do EKS. A raiz configura os providers kubernetes e helm com ele."
  value       = module.cluster.cluster_endpoint
}

output "cluster_ca_data" {
  description = "CA do cluster, base64. Par obrigatorio do endpoint na configuracao dos providers."
  value       = module.cluster.cluster_ca_data
}

output "region" {
  description = "Regiao da celula."
  value       = var.region
}

output "argocd_namespace" {
  description = "Namespace do ArgoCD."
  value       = local.install_argocd ? module.argo_cd[0].namespace : null
}

output "eso_namespace" {
  description = "Namespace do External Secrets."
  value       = local.install_external_secrets ? module.external_secrets[0].namespace : null
}

output "crossplane_namespace" {
  description = "Namespace do Crossplane."
  value       = local.install_crossplane ? module.crossplane[0].namespace : null
}

output "kubeconfig_command" {
  description = "Comando que escreve o contexto deste cluster no kubeconfig local."
  value       = "aws eks update-kubeconfig --name ${module.cluster.cluster_name} --region ${var.region} --profile ${var.aws_profile}"
}

# --------------------------------------------------------------------------------------
# 3.1 — a interface com a fase 3.2 (lado hub). Os dois valores sao calculados, nao lidos
# do recurso, entao a 3.2 pode ser escrita antes de o NLB existir.
# --------------------------------------------------------------------------------------

output "ingress_private_ips" {
  description = "Enderecos fixos do NLB interno, um por AZ. E o que a target group do hub registra."
  value       = module.ingress.private_ips
}

output "ingress_target_group_arn" {
  description = "ARN da target group do gateway. Mesmo valor que o ConfigMap entrega ao GitOps."
  value       = module.ingress.target_group_arn
}

output "ingress_security_group_id" {
  description = "SG do NLB interno. Origem das regras que o SG do cluster autoriza."
  value       = module.ingress.security_group_id
}

output "cell_ingress_fqdn" {
  description = <<-EOT
    O wildcard desta celula — o que o certificado do ACM cobre e o que o Gateway do Istio
    aceita. Nao e um nome resolvivel: para o teste de aceite, use cell_services_url.
  EOT
  value       = local.cell_wildcard
}

output "cell_services_url" {
  description = <<-EOT
    O aceite da celula inteira: um curl NESTA url, da internet, sem tunel e sem -k, tem de
    devolver 200. A cadeia que ele prova e ALB do hub -> TGW -> NLB interno -> Envoy -> pod.
  EOT
  value       = local.install_httpbin ? one(module.httpbin[*].url) : null
}

output "cell_certificate_arn" {
  description = "Certificado da celula, anexado ao listener :443 compartilhado por SNI. Sai do validation, nao do certificate — e o unico que espera a validacao."
  value       = aws_acm_certificate_validation.cell.certificate_arn
}

output "hub_target_group_arn" {
  description = "Target group do lado HUB, na conta network, apontando para os enderecos fixos do NLB da spoke. Nome gerado por name_prefix, entao o ARN muda a cada recriacao — ler daqui, nunca fixar."
  value       = aws_lb_target_group.hub_to_cell.arn
}

output "hub_listener_rule_priority" {
  description = "Priority da rule desta celula no listener compartilhado. Derivada do nome; colisao entre celulas falha alto no apply, o que e o comportamento desejado."
  value       = local.listener_rule_priority
}

output "transit_gateway_id_in_use" {
  description = "O TGW que esta celula anexou. Existe para a raiz assertar que ele veio do hub, nao de valor fixo."
  value       = var.transit_gateway_id
}

output "api_authorized_cidr" {
  description = "Origem autorizada em 443 no SG do cluster. Existe pela mesma razao do output acima."
  value       = var.hub_vpc_cidr_block
}

output "helm_release_names" {
  description = "Par namespace/nome de cada release desta celula. Existe so para o guard offline de colisao — o mock_provider do helm nao mantem estado de releases."
  value = compact([
    local.install_load_balancer_controller ? "kube-system/aws-load-balancer-controller" : "",
    local.install_ingress_istio ? "istio-system/istio-base" : "",
    local.install_ingress_istio ? "istio-system/istiod" : "",
    local.install_ingress_istio ? "istio-ingress/istio-ingress" : "",
    local.install_ingress_istio ? "istio-ingress/inbound" : "",
    local.install_target_group_binding ? "istio-ingress/target-group-binding" : "",
    local.install_httpbin ? "httpbin/httpbin" : "",
    local.install_external_secrets ? "external-secrets/external-secrets" : "",
    local.install_argocd ? "argocd/argo-cd" : "",
    local.install_crossplane ? "crossplane-system/crossplane" : "",
  ])
}

# Reexportados para regions/<regiao> conseguir testar o repasse de endpoint_public_access/
# public_access_cidrs sem precisar alcancar module.cluster de dois niveis acima (fronteira de
# modulo nao e transparente — mesmo motivo de cluster_endpoint/cluster_ca_data acima).
output "endpoint_public_access" {
  description = "Se o endpoint da API do EKS esta exposto na internet."
  value       = module.cluster.endpoint_public_access
}

output "public_access_cidrs" {
  description = "CIDRs autorizados no endpoint publico, quando aberto."
  value       = module.cluster.public_access_cidrs
}
