# 02 — Records and Alias

**Pilar WAF principal:** Reliability (records corretos = resolução previsível para o LB certo).

## A-alias vs. CNAME — por que alias

Para apontar um nome ao load balancer do cluster (NLB/ALB, cujo IP muda), há dois caminhos:

| | **A-alias** (Route53) | **CNAME** |
|---|---|---|
| Aponta para | recurso AWS (NLB/ALB/CloudFront) por nome lógico | outro nome DNS |
| Funciona no apex (`blue.aws.example.com`)? | **sim** | **não** (CNAME é proibido no apex) |
| Custo de query | grátis (alias é interno ao Route53) | cobrado como query normal |
| Resolução | Route53 resolve ao IP atual do LB automaticamente | 1 hop DNS a mais |

Alias é a escolha padrão: funciona no apex, é grátis, e acompanha o IP do LB sem intervenção.
CNAME só quando o alvo é um domínio externo fora do Route53.

## O A-alias para um NLB precisa de dois dados

Um alias record não guarda um IP — guarda uma **referência** ao LB, que exige:

```text
Record:  *.blue.aws.example.com   A (alias)
  AliasTarget:
    DNSName:      <nlb-hostname>            ← o FQDN do NLB (muda por deploy do LB)
    HostedZoneId: <canonicalNlbZoneId>      ← zona CANÔNICA do ELB, POR REGIÃO — NÃO é a subzona
    EvaluateTargetHealth: true
```

O `HostedZoneId` do AliasTarget é a **zona canônica do serviço ELB naquela região**
(`us-east-1` = `Z26RNL4JYFTOTI`, valor fixo publicado pela AWS), **não** o ID da sua subzona.
Trocar um pelo outro é um erro comum que faz o alias apontar para lugar nenhum. Ver apêndice
para o valor real da PoC.

## Wildcard — um record, todos os apps

O wildcard é o que torna o deploy de um app novo **zero-touch em DNS**:

```text
*.blue.aws.example.com   A-alias → NLB   cobre  app1.blue..., app2.blue..., qualquer-um.blue...
```

Criar a subzona + o wildcard **uma vez**; a partir daí cada app novo só existe como host/rota
no cluster e já resolve. É a materialização do "nomes estáveis sem tocar a pai a cada deploy"
(tópico 0). O wildcard é **opcional na criação** — só faz sentido quando o hostname do NLB já
é conhecido; antes disso, criar a subzona sem ele e adicionar quando o LB subir.

## O problema do apex — o wildcard NÃO cobre a raiz da subzona

Pegadinha real (observada na PoC): `*.blue.aws.example.com` cobre `foo.blue...` mas **não**
cobre o **apex** `blue.aws.example.com` em si. São nomes diferentes para o DNS.

```text
*.blue.aws.example.com   →  resolve foo.blue..., bar.blue...   ✅
blue.aws.example.com     →  NÃO coberto pelo wildcard          ❌  (é o apex da subzona)
```

Se algo precisa responder **no apex** (ex.: roteamento por path em `blue.aws.example.com/health`):

1. **Record A do apex** explícito (alias→NLB), além do wildcard.
2. **Certificado** com o apex no SAN — o cert wildcard `*.blue...` também não cobre o apex
   (tópico 4).
3. Rota/Gateway no cluster escutando o host do apex.

O mesmo vale para TLS: SAN wildcard e SAN apex são entradas distintas. Cobrir o apex é uma
decisão consciente, não um efeito colateral do wildcard.

## TTL dos app records

- App records (o wildcard, records por app) podem ter **TTL baixo** (60s) em ambiente
  dinâmico — permite repontar rápido se o LB mudar.
- Em produção estável, subir o TTL reduz volume de query (custo) — trade-off entre agilidade
  e custo, decidido por ambiente.

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **REL** resolução previsível | A-alias acompanha o IP do LB; `EvaluateTargetHealth` tira LB doente da resposta |
| **OPS** deploy zero-touch em DNS | wildcard cobre apps novos sem novo record |
| **COST** | alias não é cobrado por query; TTL ajustável por ambiente |
| **REL** apex explícito | Record A + SAN do apex evitam "resolve o subdomínio mas não a raiz" |

## Próximo

→ [`03-private-and-cross-account.md`](03-private-and-cross-account.md): resolução interna que
não sai da VPC, inclusive cross-account.
