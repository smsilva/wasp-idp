# 05 — DNS

**Pilar WAF principal:** Operational Excellence (nomes estáveis e delegação) + Reliability
(resolução HA).

## Dois DNS diferentes — não confundir

| Tipo | Route53 | Propósito | Nesta referência |
|---|---|---|---|
| **Público** | Public Hosted Zone | Expor serviços na internet com nome estável (`app.<spoke-domain>`) | Cada spoke/cluster ganha uma **subzona pública** delegada |
| **Privado** | Private Hosted Zone (PHZ) | Resolver nomes internos da VPC, não visíveis na internet | Opcional, por spoke — nomes corporativos/internos |

O caso central desta referência é o **público delegado** (cada cluster vira alvo de deploy
com seu próprio domínio). O privado entra quando há resolução interna cross-account/on-prem.

## DNS público por spoke — delegação

```text
Zona raiz (pai)  <root-domain>          ex.: aws.example.com   [gerenciada centralmente]
   │  NS record delegando a subzona
   ▼
Subzona (spoke)  <spoke>.<root-domain>  ex.: blue.aws.example.com   [criada com o cluster]
   │  wildcard  *.<spoke>.<root-domain>  A-alias → NLB/ALB do cluster
   ▼
   app1.blue.aws.example.com, app2.blue.aws.example.com, ...
```

**Peças por spoke:**

1. **Hosted Zone** da subzona `<spoke>.<root-domain>`.
2. **Record NS** na zona **pai** delegando a subzona (é o que torna a subzona resolvível
   globalmente — sem ele, a subzona existe mas ninguém a encontra).
3. **Record wildcard** `*.<spoke>.<root-domain>` → A-alias para o load balancer do cluster
   (NLB/ALB). Opcional: só criar se o hostname do LB for conhecido.

Isso permite que cada app do cluster tenha um FQDN estável sem tocar na zona pai a cada
deploy — o wildcard resolve tudo. Alinhado ao **composable design**: a responsabilidade de
DNS é uma abstração isolada (um XR `DnsZone`, ver tópico 7), filha do Cluster.

## DNS privado (opcional)

Quando o spoke precisa resolver nomes internos (não expostos):

- **Private Hosted Zone** associada à VPC do spoke — queries do domínio resolvem só dentro
  da VPC.
- **Route53 Resolver outbound endpoint** + regras de forwarding — encaminha domínios
  corporativos para resolvers externos (on-prem via VPN). Requer subnets privadas em **≥2
  AZs** (exigência AWS de 2 IPs em subnets distintas).
- **Resolução cross-account**: PHZ pode ser associada a VPCs de outras contas via
  `VPCAssociationAuthorization` — útil quando um serviço central resolve nomes de vários
  spokes.

## Zona pai compartilhada — cuidado

Se a zona raiz é **compartilhada** entre times (comum), a regra do PoC vale: **só ADICIONAR**
records isolados (o NS da sua subzona), **nunca** alterar records de terceiros. Ferramentas
como external-dns devem ser escopadas (`--domain-filter`, `--zone-id-filter`, `--txt-owner-id`)
para não pisar em registros de outros donos. Ver apêndice para os valores reais da PoC.

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **OPS** nomes estáveis | subzona + wildcard = FQDN por app sem mexer na zona pai a cada deploy |
| **REL** resolução HA | Route53 é global e HA por design; resolver endpoint multi-AZ |
| **[SEC05 — Protecting networks](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/protecting-networks.html)** | PHZ resolve só dentro da VPC; público e privado separados |
| **Composable** | DNS como XR isolado (`DnsZone`), não embutido no provisionamento de rede |

## Próximo

→ [`06-security.md`](06-security.md): SG, NACL, Flow Logs e endpoints privados.
