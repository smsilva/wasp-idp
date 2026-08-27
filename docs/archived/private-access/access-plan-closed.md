# Private Access And Ingress Plan Closed

_2026-08-26_


Frente inteira desenhada e escrita como plano executável em quatro fases, sem decisão de desenho em
aberto. Ordem descoberta, não presumida: o acesso privado subiu para antes do ingress quando ficou
claro que **quem fala com o API server é o Terraform**, não o operador.

Nove decisões fechadas — ingress único pelo hub, VPN por cliente, Client VPN com SAML, T1 permanente
durante o dia, fronteira de state por ciclo de vida, ingress variante B, wildcard de ACM por cluster,
subzona `nonprod.` com delegação em código, e cliente simulado no Azure com os dois lados do túnel
numa raiz só.

Quatro achados que mudaram o rumo:

- **O desenho de referência não tem ingress no hub** — o hub dele é trânsito puro, sem VPC. Ingress
  centralizado ficou sem precedente interno, e a decisão foi tomada sabendo disso.
- **Route table de tenant só isola nas duas direções se o attachment for por cliente.** Com attachment
  agregado, a entrada depende de security group — uma camada, a mais interna.
- **`TargetGroupBinding` aceita target group externo**, o que permite Terraform ser dono do NLB sem
  quebrar o apply único.
- **O ALB não lê Secret do Kubernetes**, o que move o certificado público do cert-manager para o ACM e
  encerra a emissão por cluster.

Fechou também o item aberto desde a camada 2: **o corte `hub | spoke+cluster` sobrevive ao TGW**.
