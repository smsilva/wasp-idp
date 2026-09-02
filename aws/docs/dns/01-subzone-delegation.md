# 01 — Subzone Delegation

**Pilar WAF principal:** Operational Excellence (delegação = autonomia sem acesso à zona pai).

## O que "delegar" significa

Criar a Hosted Zone da subzona **não basta** — ela existe, mas ninguém a encontra. A subzona
só se torna resolvível globalmente quando a zona **pai** aponta para os name servers dela, via
um **record NS**. Delegar é escrever esse único record na pai:

```text
Criar Hosted Zone blue.aws.example.com  →  Route53 atribui 4 name servers:
    ns-123.awsdns-45.com, ns-678.awsdns-90.net, ...

Na zona PAI (aws.example.com), adicionar:
    blue   NS   ns-123.awsdns-45.com.
                ns-678.awsdns-90.net.
                ... (os 4 NS da subzona)   TTL 60-300
```

A partir daí, uma query por `app.blue.aws.example.com` segue a cadeia: raiz → pai (que
responde "pergunte aos NS da subzona") → subzona (que responde o IP). Sem o record NS, a pai
não sabe delegar e a query morre em `NXDOMAIN`.

## Os 4 name servers e por que não editá-los

Route53 atribui **4 name servers** por Hosted Zone (redundância — REL). O record NS na pai
deve listar **exatamente** esses 4, copiados da subzona recém-criada. Erros comuns:

- **Copiar NS de outra zona** → delegação aponta para servers que não são autoritativos da
  subzona → resolução falha intermitente.
- **Editar/reduzir a lista** → perde redundância; se um NS ficar indisponível, resolução
  degrada.

No fluxo declarativo, o record NS é criado **lendo** os NS da subzona (`Zone.status`), não
hardcoded — o XR `DnsZone` (tópico 6) faz exatamente isso.

## TTL da delegação

- **TTL baixo (60–300s)** no record NS **enquanto o ambiente é efêmero/em teste** — permite
  recriar a subzona e re-delegar sem esperar cache global expirar.
- TTL mais alto (horas) só quando a delegação é estável e raramente muda (produção
  consolidada). Delegação é infraestrutura de longa vida; app records (tópico 2) é que variam.

## Glue records — quando importam (e aqui não)

Glue é necessário quando os name servers da subzona estão **dentro** da própria subzona
(`ns1.blue.aws.example.com`) — a pai precisa do IP "colado" para quebrar a circularidade. Com
Route53, os NS atribuídos são `awsdns-*` (fora da subzona), então **glue não se aplica** — um
detalhe que só reaparece se alguém rodar name servers próprios. Mencionado para fechar o
assunto, não porque é necessário nesta referência.

## Zona pai compartilhada — a regra imutável

Quase sempre a pai é **compartilhada** entre times. Aí vale a regra herdada do PoC
([`CLAUDE.md`](../../CLAUDE.md)): **só ADICIONAR** o record NS da **sua** subzona; **nunca** tocar,
sobrescrever ou remover records de terceiros na pai.

```text
Permitido na pai:   ADICIONAR  blue   NS  → (os 4 NS da subzona blue)   ✅
Proibido na pai:    alterar/remover  outrotime.aws.example.com          ❌
```

Consequência prática: qualquer automação que escreva na pai (external-dns, Crossplane) deve
ser **escopada** para tocar só o próprio domínio — tópicos 4 e 5. Um external-dns sem
`--domain-filter`/`--zone-id-filter` numa zona compartilhada é um acidente esperando acontecer.

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **OPS** autonomia com contenção | subzona delegada = o cluster gerencia seus nomes sem acesso de escrita à pai (só o NS) |
| **REL** redundância de resolução | 4 name servers por zona, listados na íntegra |
| **SEC** só ADICIONAR | delegação escreve 1 record isolado na pai; nunca altera de terceiros |

## Próximo

→ [`02-records-and-alias.md`](02-records-and-alias.md): que records apontam apps ao cluster —
alias, wildcard e o problema do apex.
