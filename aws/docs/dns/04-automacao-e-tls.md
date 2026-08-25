# 04 — Automação de DNS e TLS

**Pilar WAF principal:** Operational Excellence (records e certificados sem toil manual).

## Duas automações que dependem do DNS

Depois que a subzona está delegada (tópico 1) e o wildcard aponta ao NLB (tópico 2), duas
peças no cluster tiram o humano do loop:

| Automação | Faz | Depende do DNS para |
|---|---|---|
| **external-dns** | publica A-records por app conforme Service/Ingress aparecem | escrever na subzona (escopado) |
| **cert-manager** (DNS-01) / **ACM** | emite certificados TLS | provar posse do domínio via TXT na zona autoritativa |

As duas escrevem em Route53 — e numa zona pai **compartilhada** o escopo correto é o que
separa "funciona" de "pisou no record de outro time".

## external-dns — sources e escopo

- **Sources** (`--source`): external-dns descobre o que publicar a partir de `Service`,
  `Ingress` (e, com config, outros). Config típica da plataforma: `--source=service,ingress`.
  **Não** descobre `Gateway`/`VirtualService` do Istio nativamente — se a exposição é via
  Istio, ou se usa o modelo wildcard (o record já existe, não precisa de external-dns por
  app), ou um Ingress-fantasma publica o A-record (gotcha real — ver apêndice). O modelo
  **preferido** é o **wildcard da subzona**, que elimina o external-dns por app.
- **Escopo obrigatório numa zona compartilhada** — três flags, sempre juntas:

```text
--domain-filter=<root-domain>       só age em records desse domínio
--zone-id-filter=<parent-zone-id>   só na zona certa (NÃO é value first-class no chart — via extraArgs)
--txt-owner-id=<owner>              marca cada record como "meu"; não toca records sem essa marca
```

O `--txt-owner-id` é o que dá **posse**: external-dns cria um TXT-registro companheiro por
record, e só gerencia records cujo TXT tem o owner dele. Dois external-dns na mesma zona com
owners distintos coexistem sem se pisar. **Confirmar nos logs do pod** (`ZoneIDFilter:[<id>]`,
`domainFilter`), não só no manifesto — o `zoneIdFilters` cai em silêncio se posto no lugar
errado do chart (gotcha do apêndice).

- **`policy: upsert-only`** — external-dns **nunca deleta** records automaticamente, nem
  quando o Service que os gerou some. Rede de segurança contra deleção acidental em massa numa
  zona compartilhada; o preço é **limpeza manual** de records de teste
  (`change-resource-record-sets` com `Action: DELETE`).

## cert-manager DNS-01 — e o issuer por subzona

Para um certificado **wildcard** (`*.blue.aws.example.com`), o desafio HTTP-01 não serve
(não há um host único) — usa-se **DNS-01**: a CA (Let's Encrypt) pede que se prove posse
escrevendo um TXT `_acme-challenge` na zona **autoritativa** do domínio.

Aqui está o gotcha estrutural (observado na PoC): um `ClusterIssuer` **compartilhado** com
`hostedZoneID` fixo da **pai** escreve o TXT na **pai** — mas a **subzona** é autoritativa →
Let's Encrypt procura o TXT na subzona, não acha, e o desafio fica eterno em
`Waiting for DNS-01 challenge propagation`.

```text
Errado:  ClusterIssuer compartilhado → TXT na PAI → subzona é autoritativa → LE não acha ❌
Certo:   ClusterIssuer POR SUBZONA (hostedZoneID = o da subzona) → TXT na subzona ✅
```

**Fix (regra):** um `ClusterIssuer` **por ambiente/subzona**
(`letsencrypt-dns-route53-<spoke>`) com o `hostedZoneID` da **subzona**; a policy IAM do
cert-manager precisa incluir o ARN da subzona. E **nunca editar o issuer compartilhado** —
outros certs dependem dele (e o classifier de auto-mode bloqueia a edição).

## O apex de novo — cert wildcard não cobre a raiz

Coerente com o tópico 2: o SAN `*.blue.aws.example.com` **não** cobre `blue.aws.example.com`.
Se o apex precisa de TLS (roteamento por path na raiz da subzona), o certificado precisa do
**apex explícito no SAN**, além do wildcard.

## cert-manager (DNS-01) vs. ACM — quando cada um

| | **cert-manager + Let's Encrypt** | **AWS Certificate Manager (ACM)** |
|---|---|---|
| Onde o cert vive | Secret no cluster (usado por Istio/Ingress) | no serviço AWS (ALB, CloudFront, APIM) |
| Renovação | cert-manager renova sozinho | ACM renova sozinho |
| Uso nesta PoC | TLS terminando **no cluster** (wildcard por subzona) | quando o TLS termina num **LB/edge AWS** |

Regra prática: TLS que termina **dentro** do cluster → cert-manager DNS-01; TLS que termina
num **recurso AWS gerenciado** (ALB/CloudFront) → ACM com validação DNS (um CNAME na subzona).
Ambos provam posse via DNS — daí este tópico morar no domínio DNS.

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **OPS** eliminar toil | external-dns publica records; cert-manager/ACM renovam certs sozinhos |
| **[SEC08-BP01](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_protect_data_rest_key_mgmt.html)** TLS em toda exposição | wildcard cert por subzona; apex no SAN quando preciso |
| **SEC** contenção em zona compartilhada | escopo `--txt-owner-id`/`--zone-id-filter`; issuer por subzona; upsert-only |
| **OPS** observabilidade da automação | validar escopo nos **logs do pod**, não só no manifesto |

## Próximo

→ [`05-seguranca-de-dns.md`](05-seguranca-de-dns.md): IAM do Route53, DNSSEC e query logging.
