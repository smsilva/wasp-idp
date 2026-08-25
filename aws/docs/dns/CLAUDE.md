# CLAUDE.md — `dns/` (Domain: DNS)

> Índice do domínio de **DNS** — como nomes estáveis chegam aos serviços de cada spoke, do
> registro público delegado à resolução privada cross-account, com automação no cluster e
> TLS. Ordem de leitura = ordem dos arquivos. Corpo genérico (placeholders `<...>`).

## O que este domínio entrega

Um **nome estável e resolvível** para cada app de cada cluster, sem tocar na zona pai a cada
deploy, e uma **resolução privada** para nomes internos que não devem sair da VPC. Onde
`../network/05-dns.md` trata DNS como um **concern de rede** (a subzona por spoke dentro da
topologia), este domínio o trata como **peça de primeira classe**: a mecânica de delegação, o
contrato de registros (alias/apex/wildcard), a resolução cross-account, a automação
(external-dns) e a emissão de certificados (cert-manager/ACM) que depende do DNS.

Não repete a topologia de subzona por spoke (isso é `../network/05`); parte dali e aprofunda o
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

## Sequência de construção (nome resolvível → app com TLS)

```text
① Zona pai pública existe e é gerenciada centralmente (<root-domain>) — não a criamos
② Por spoke/cluster: criar a Hosted Zone da subzona <spoke>.<root-domain>
③ Delegar: Record NS da subzona NA zona pai (só ADICIONAR — nunca alterar records de outros)
④ Wildcard *.<spoke>.<root-domain> A-alias → NLB do cluster (canonicalNlbZoneId da região)
⑤ external-dns no cluster publica A-records por app, escopado à subzona (nunca à pai inteira)
⑥ cert-manager DNS-01 (ou ACM) emite o certificado wildcard, autoritativo NA subzona
⑦ (opcional) Private Hosted Zone + Resolver para nomes internos/on-prem
```

## Estado atual vs. alvo (resumo)

- **Hoje no PoC:** external-dns + cert-manager publicam/certificam sob uma zona pai
  **compartilhada** (`<root-domain>`); a subzona por ambiente é criada via
  `provider-aws-route53` (`Zone`/`Record`), mas **não** há um XR `DnsZone` de alto nível — a
  lógica está espalhada. Ver `../../CLAUDE.md` (fatia 2, "DNS fixado").
- **Alvo desta referência:** um XR **`DnsZone`** (Zone + Record NS na pai + wildcard),
  **filho do Cluster**, composable e isolado — a responsabilidade de DNS deixa de ser
  espalhada e vira uma abstração (decisão ratificada).
- **Gaps já mapeados:** zona pai compartilhada exige escopo rígido do external-dns
  (`--zone-id-filter`/`--txt-owner-id`); o issuer DNS-01 precisa ser **por subzona** (o
  compartilhado escreve o TXT na zona errada) — tópicos 4 e 5.

## Relação com o resto do repo

- **Depende de** `../network/` (a subzona vive na topologia do spoke; o wildcard aponta ao
  NLB do cluster) e `../security/` (IAM do external-dns/cert-manager, Pod Identity, segredos).
- **Serve** o futuro domínio Compute (o cluster expõe apps sob a subzona) e a exposição
  pública fim-a-fim.
- Regra herdada do PoC (`../../CLAUDE.md`): numa zona pai **compartilhada**, só ADICIONAR
  records isolados (o NS da própria subzona); **nunca** alterar records de terceiros.
