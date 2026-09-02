# CLAUDE.md — `dns/` (Domain: DNS)

> Regras e convenções do domínio de **DNS** — como nomes estáveis chegam aos serviços de
> cada spoke, do registro público delegado à resolução privada cross-account, com
> automação no cluster e TLS. Corpo genérico (placeholders `<...>`). Índice de leitura em
> [`README.md`](README.md).

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

## Delegação verificada na prática (2026-08-26)

Primeira subzona delegada de verdade — apex no Azure DNS, subzona no Route 53, delegação em
Terraform (`aws/terraform/dns/`). Três coisas que só apareceram executando:

- **O TTL da delegação é o do NS na PAI, não o da subzona.** O record `NS` que nasce **dentro** da
  hosted zone do Route 53 vem com TTL 172800 (default da AWS) e não se mexe nele. Quem governa quão
  rápido a delegação repropaga é o registro na zona pai — configurar 300 lá é o que permite recriar a
  subzona sem o edge ficar horas intermitente.
- **Conferir a delegação com `dig +trace`, não `dig NS`.** O `+trace` mostra o *handoff*: o name
  server da pai entregando a delegação e o do Route 53 respondendo o SOA. O `dig NS` sozinho pode vir
  de cache e não prova quem é autoritativo.
- **Zona pai costuma já ter delegações NS de outros ambientes.** Antes de criar, checar se já existe
  um `NS <label>` — um record set preexistente colide no apply, e a mensagem de erro do Azure não
  aponta a causa. Só ADICIONAR ao lado; nunca alterar o do vizinho.

## Relação com o resto do repo

- **Depende de** `../network/` (a subzona vive na topologia do spoke; o wildcard aponta ao
  NLB do cluster) e `../security/` (IAM do external-dns/cert-manager, Pod Identity, segredos).
- **Serve** o futuro domínio Compute (o cluster expõe apps sob a subzona) e a exposição
  pública fim-a-fim.
- Regra herdada do PoC (`../../CLAUDE.md`): numa zona pai **compartilhada**, só ADICIONAR
  records isolados (o NS da própria subzona); **nunca** alterar records de terceiros.

## TLS no edge: o ALB só lê ACM

- **O ALB não consegue consumir Secret do Kubernetes** — só certificado do ACM. Importar o
  certificado do cert-manager no ACM funciona, mas transfere a renovação (~60 dias) para nós.
  Preferir **certificado do ACM com validação por DNS**, que renova sozinho enquanto o CNAME
  permanecer na zona.
- **Wildcard cobre um nível só, e `*.*.` não existe.** `*.zona` não cobre `app.<id>.zona` — se o
  padrão de nome tem dois níveis, é **um wildcard por cluster** (`*.<id>.zona`), não um global.
- **O ALB não valida o certificado do backend.** No trecho ALB → NLB → gateway, autoassinado basta;
  não precisa ser confiável nem casar com hostname.
- **A subzona delegada é a fronteira de blast radius do DNS** — dar ao external-dns acesso só a ela
  impede que ele toque o apex. Delegar o domínio inteiro elimina essa separação.
- **Certificado do ACM tem de estar na mesma conta e região do load balancer** que o serve. Isso
  arrasta a hosted zone pública para a conta do edge (`network`): zona noutra conta torna cada
  renovação um trabalho cross-account.
