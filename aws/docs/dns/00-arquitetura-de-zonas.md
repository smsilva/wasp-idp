# 00 — Arquitetura de Zonas

**Pilar WAF principal:** Operational Excellence (nomes estáveis, hierarquia gerenciável).

## Duas árvores de DNS, propósitos distintos

Route53 serve dois mundos que não se misturam — confundi-los é a origem de "resolve na minha
máquina mas não no cluster" (e vice-versa):

| | **Public Hosted Zone** | **Private Hosted Zone (PHZ)** |
|---|---|---|
| Visibilidade | internet inteira | só VPCs associadas |
| Resolve | `app.<spoke>.<root-domain>` | nomes internos (`db.internal`, corporativos) |
| Autoridade | delegada da zona pai pública | associada a VPC(s), sem delegação pública |
| Caso central aqui | **sim** — cada cluster é alvo de deploy com FQDN próprio | opcional — resolução interna/on-prem |

Uma query resolve na árvore **pública** se vier da internet; resolve na **privada** se vier
de dentro de uma VPC associada à PHZ (a PHZ tem precedência sobre a pública para aquele
domínio, dentro da VPC). São namespaces separados que podem até compartilhar o nome de
domínio com respostas diferentes — *split-horizon DNS*.

## Por que delegar, e não uma zona única gigante

A tentação é pôr todos os apps de todos os clusters numa zona só. Não escala e viola o
isolamento:

```text
Zona única (antipadrão)                 Delegação por spoke (esta referência)
  aws.example.com                          aws.example.com                  [pai, central]
    app1.blue  ← todos os times              │ NS → blue.aws.example.com     [subzona spoke]
    app2.green    escrevem na                 │ NS → green.aws.example.com    [subzona spoke]
    app3.blue     MESMA zona                  ▼
    ...           (colisão, blast radius)   cada spoke dono da sua subzona
```

Delegar dá:

- **Isolamento de blast radius** — um erro na subzona `blue` não afeta `green` nem a pai.
- **Autonomia** — o cluster cria/gerencia seus records sem permissão de escrita na pai
  (exceto o **único** record NS de delegação — tópico 1).
- **Composable** — a subzona é uma abstração isolada (o XR `DnsZone`, tópico 6), filha do
  Cluster, não um bloco na zona central.

## Hierarquia nesta referência

```text
<root-domain>                 ex.: aws.example.com        [pai, gerenciada centralmente]
  └─ <spoke>.<root-domain>    ex.: blue.aws.example.com   [subzona, criada com o cluster]
       └─ *.<spoke>...        wildcard → NLB do cluster    [1 record cobre todos os apps]
            ├─ app1.blue.aws.example.com
            └─ app2.blue.aws.example.com  ...
```

O **wildcard** é o que dá FQDN estável por app sem tocar na zona pai a cada deploy: a subzona
é criada uma vez, o wildcard aponta ao load balancer uma vez, e cada app novo só precisa
existir como host no cluster — o DNS já resolve. Detalhe do wildcard e do apex: tópico 2.

## Onde a raiz vive (e por que não a criamos)

A zona pai (`<root-domain>`) é **premissa**, gerenciada centralmente (muitas vezes
compartilhada entre times). Esta referência **não a cria** — ela consome a delegação. Se a
raiz real está num provedor diferente (ex.: a zona corporativa em outro DNS/cloud), a âncora
pública deve ser uma zona **na própria conta AWS**, para que a delegação seja self-service e
não exija abrir chamado/console externo a cada ambiente (ver apêndice — foi exatamente a
decisão da PoC de ancorar sob `<root-domain>`, não sob o domínio Azure pai).

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **OPS** nomes estáveis | subzona + wildcard = FQDN por app sem mexer na pai a cada deploy |
| **OPS** hierarquia gerenciável | delegação isola cada spoke; a pai só guarda os NS |
| **[SEC05 — Protecting networks](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/protecting-networks.html)** | público e privado em árvores separadas; split-horizon quando preciso |
| **REL** resolução global | Route53 é global e HA por design |

## Próximo

→ [`01-delegacao-de-subzonas.md`](01-delegacao-de-subzonas.md): a mecânica do record NS que
torna a subzona resolvível.
