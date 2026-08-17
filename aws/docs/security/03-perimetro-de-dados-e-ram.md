# 03 — Perímetro de Dados e RAM

**Pilar WAF principal:** Security (SEC03 — permissões; contenção de acesso cross-account).

## Dois lados de toda fronteira: identidade e recurso

O tópico 2 cobriu o lado da **identidade** (quem assume o quê). Este cobre o lado do
**recurso**: o que o recurso-alvo aceita, independentemente de quem pede. As duas policies
se somam num **AND**:

```text
Identity policy (na origem)  diz "esta identidade PODE agir sobre o recurso X"
Resource policy (no destino) diz "o recurso X ACEITA esta identidade"
        → acesso só acontece se AMBAS permitirem (cross-account)
```

Cross-account, a resource policy é **obrigatória** — uma identity policy sozinha não fura a
fronteira da conta. (Same-account, uma das duas basta; a resource policy é o que habilita o
cross-account.)

## Resource-based policies

São policies anexadas ao **recurso**, não à identidade. Exemplos: bucket policy (S3), key
policy (KMS), trust policy (a de role já vista), policy de fila (SQS). Todas respondem "quem,
de fora, pode me acessar". O perímetro de dados nasce de escrevê-las restritivas:

- **`Principal` explícito** — a conta/role exata, nunca `"*"` sem condição.
- **Condição de Organization** — `aws:PrincipalOrgID` limita a qualquer principal **da sua
  Organization**, útil quando a lista de contas cresce:

```json
{
  "Effect": "Allow",
  "Principal": "*",
  "Action": "s3:GetObject",
  "Resource": "arn:aws:s3:::<bucket>/*",
  "Condition": {
    "StringEquals": { "aws:PrincipalOrgID": "<org-id>" }
  }
}
```

`Principal: "*"` **com** a condição `aws:PrincipalOrgID` não é acesso público — é "qualquer um
da minha Organization". Sem a condição, seria exposição aberta (o Access Analyzer sinaliza —
tópico 6).

## AWS RAM — compartilhar recurso, não copiar

O **Resource Access Manager** compartilha um recurso de uma conta com outras **sem duplicá-lo**.
É o mecanismo pelo qual o TGW do Hub (`../network/03`) fica acessível às contas de projeto:

| Objeto RAM | Papel |
|---|---|
| `ResourceShare` | o contêiner do compartilhamento (`ram-share-tgw-<region>-<tenant>`) |
| `ResourceAssociation` | associa **o recurso** (o TGW) ao share |
| `PrincipalAssociation` | associa **quem recebe** (o account ID do spoke) ao share |

### `allowExternalPrincipals=false` — o perímetro

A trava central de segurança do RAM:

```text
allowExternalPrincipals = false   → só contas da MESMA Organization aceitam o share
allowExternalPrincipals = true    → qualquer account ID pode ser adicionada (evitar)
```

Fixar `false` garante que um erro de digitação num account ID **fora** da Organization
simplesmente não compartilha nada — o perímetro é a Organization, e o RAM o respeita por
construção. Combina com o SCP e com o `aws:PrincipalOrgID`: mesmo perímetro, três camadas.

## Modelo descentralizado (herdado do network)

Coerente com `../network/03`: o **próprio provisionamento do spoke** cria o RAM share na conta
Hub (via role cross-account do tópico 2), escopado à account daquele tenant. O Hub não mantém
lista de tenants; remover o tenant remove o share. Vantagem de segurança: nenhum share
"largo" pré-existente esperando um principal errado — cada share nasce já restrito a um
account ID.

## Nesta PoC (conta única)

RAM não é exercido enquanto hub e spoke são a mesma conta — o share é suprimido
automaticamente (`../network/03`, "cenário de conta única"). O perímetro de dados via
`aws:PrincipalOrgID` também só passa a valer quando existir uma Organization com mais de uma
conta (`../accounts/`). Hoje: mapa; amanhã: código.

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **SEC03-BP07** limitar acesso cross-account | resource policy com `Principal` explícito + `aws:PrincipalOrgID` |
| **SEC03-BP09** compartilhar recursos com segurança | RAM com `allowExternalPrincipals=false` (só a Organization) |
| **SEC03-BP01** menor privilégio | share escopado por tenant (account ID), não aberto |

## Próximo

→ [`04-identidade-de-workload.md`](04-identidade-de-workload.md): como um pod no cluster tem
identidade sem access key montada.
