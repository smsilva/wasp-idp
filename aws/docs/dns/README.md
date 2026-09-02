# `dns/` — Domain: DNS

Índice de leitura. Convenções e regras ficam em [`CLAUDE.md`](CLAUDE.md).

## O que este domínio entrega

Um **nome estável e resolvível** para cada app de cada cluster, sem tocar na zona pai a cada
deploy, e uma **resolução privada** para nomes internos que não devem sair da VPC. Onde
[`network/05-dns.md`](../network/05-dns.md) trata DNS como um **concern de rede** (a subzona por spoke dentro da
topologia), este domínio o trata como **peça de primeira classe**: a mecânica de delegação, o
contrato de registros (alias/apex/wildcard), a resolução cross-account, a automação
(external-dns) e a emissão de certificados (cert-manager/ACM) que depende do DNS.

Não repete a topologia de subzona por spoke (isso é [`network/05-dns.md`](../network/05-dns.md)); parte dali e aprofunda o
*como* e os gotchas reais de operar Route53 numa zona pai **compartilhada**.

## Tópicos

| # | Arquivo | Assunto | Pilar WAF principal |
|---|---|---|---|
| 0 | [`00-zone-architecture.md`](00-zone-architecture.md) | Público vs. privado; hierarquia de zonas; por que delegar em vez de zona única | Operational Excellence |
| 1 | [`01-subzone-delegation.md`](01-subzone-delegation.md) | Record NS na pai, TTL, glue; zona pai compartilhada e a regra "só ADICIONAR" | Operational Excellence |
| 2 | [`02-records-and-alias.md`](02-records-and-alias.md) | A-alias vs. CNAME; wildcard; o problema do apex; alias→NLB e `canonicalNlbZoneId` | Reliability |
| 3 | [`03-private-and-cross-account.md`](03-private-and-cross-account.md) | Private Hosted Zone; Resolver endpoints; `VPCAssociationAuthorization` cross-account | Security |
| 4 | [`04-automation-and-tls.md`](04-automation-and-tls.md) | external-dns (sources, upsert-only); cert-manager DNS-01 e ACM; issuer por subzona | Operational Excellence |
| 5 | [`05-security.md`](05-security.md) | Escopo do external-dns; IAM Route53 (leitura `*`); DNSSEC; query logging | Security |
| 6 | [`06-crossplane-map.md`](06-crossplane-map.md) | O XR `DnsZone` (filho do Cluster); external-dns vs. Crossplane; estado vs. alvo | — |
