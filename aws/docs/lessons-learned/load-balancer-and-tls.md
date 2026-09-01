# Lessons learned — Load balancer and TLS

Fato + porquê, um por linha. Narrativa completa de cada achado, quando existe, em
[`docs/archived/`](../../../docs/archived/index.md).

- Tags de papel do LBC não têm fallback (controller não examina route table) — já em
  `src/network`, com teste.
- Tag `kubernetes.io/cluster/<nome>` é opcional desde o LBC `2.1.2` (só desempata VPC
  compartilhada) — fora de `src/network` de propósito, que não conhece nome de cluster.
- `TargetGroupBinding` aceita target group criado fora do controller — Terraform pode ser dono do
  NLB sem quebrar o apply único.
- Ler IPs privados de NLB é frágil (`aws_lb` não os expõe) — fixar com
  `subnet_mapping { private_ipv4_address = cidrhost(...) }`.
- ALB só lê certificado do ACM, nunca Secret do Kubernetes, e não valida certificado de backend —
  autoassinado basta no trecho ALB→NLB→gateway.
- Wildcard cobre um nível só (`*.*.` não existe) — daí um wildcard por cluster (ver
  [ADR 0010](../../../docs/adr/0010-one-acm-wildcard-per-cluster.md)).
- Um NLB por cluster, não por Service — fan-out por aplicação no mesh; hub escala por listener
  rule.
- `X-Forwarded-For` + `numTrustedProxies`: com ALB na frente, o Istio vê o IP do ALB.
- **Valor de tag do ACM é mais restrito que tag de EC2.** `*` é recusado, o erro cita índice em vez
  de nome, e nada offline pegava. Corrigido com asserção de regressão nas duas suítes (`87710af`).
  Vale para qualquer certificado wildcard futuro.
