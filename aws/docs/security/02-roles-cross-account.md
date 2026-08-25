# 02 — Roles Cross-Account

**Pilar WAF principal:** Security ([SEC02](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/identity-management.html) — identidades; [SEC03](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/permissions-management.html) — permissões cross-account).

## O problema: N contas que precisam agir umas nas outras

Num hub-and-spoke multi-account, ações cruzam fronteiras de conta o tempo todo: o Hub
compartilha o TGW com a conta de projeto (`../network/03`), a automação de uma conta cria um
attachment que a conta `network` precisa aceitar, uma pipeline central faz deploy em contas de
workload. O antipadrão é **criar um IAM user em cada conta de destino** — N credenciais de
longa duração a gerenciar e vazar. O padrão AWS é **uma role assumível**.

## `sts:AssumeRole` — a mecânica

Uma identidade na conta A assume uma role na conta B e **recebe credencial temporária de B**:

```text
Conta A (origem)                         Conta B (destino)
  identidade  ──sts:AssumeRole──►  Role  (trust policy confia em A)
              ◄── credencial STS temporária (age COMO a role de B) ──
```

Dois lados, duas policies, ambas obrigatórias:

1. **Trust policy** (na role de B) — *quem pode assumir*. É a `AssumeRolePolicyDocument`.
2. **Permissions policy** (na role de B) — *o que a role pode fazer* depois de assumida
   (menor privilégio, tópico 1).
3. Na identidade de A — um `Allow` de `sts:AssumeRole` para o ARN da role de B.

Todos os três precisam permitir. Faltando qualquer um, o assume falha.

## Trust policy escopada — não confie na conta inteira

O erro comum é confiar no `root` da conta de origem inteira:

```json
{
  "Effect": "Allow",
  "Principal": { "AWS": "arn:aws:iam::<source-account>:root" },
  "Action": "sts:AssumeRole"
}
```

Isso deixa **qualquer** principal de A assumir a role. Escope ao principal específico
(a role/user exata da automação) sempre que possível:

```json
{
  "Effect": "Allow",
  "Principal": { "AWS": "arn:aws:iam::<source-account>:role/<automation-role>" },
  "Action": "sts:AssumeRole",
  "Condition": {
    "StringEquals": { "sts:ExternalId": "<external-id>" }
  }
}
```

## `ExternalId` e o confused deputy

O **confused deputy** ocorre quando um terceiro (ex.: um SaaS) tem uma role que assume roles
em várias contas de clientes; um cliente malicioso poderia induzir o SaaS a assumir a role de
**outro** cliente. O `ExternalId` — um segredo acordado entre você e o terceiro, exigido na
trust policy via condição — quebra o ataque: o deputy só assume se apresentar o `ExternalId`
correto daquela relação.

- **Automação sua, entre suas próprias contas:** `ExternalId` é opcional (você controla os
  dois lados); escopar o `Principal` já basta.
- **Role assumível por um terceiro/SaaS:** `ExternalId` é **obrigatório** ([SEC03-BP08](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_permissions_share_securely.html)).

## Padrão nesta referência: Hub ↔ conta de projeto

| Direção | Role na conta | Confia em | Faz |
|---|---|---|---|
| Projeto → Hub | `<prefix>-hub-share` (Hub) | automação da conta de projeto | criar RAM share / aceitar attachment do TGW |
| Hub → projeto (raro) | `<prefix>-hub-reader` (projeto) | automação do Hub | leitura de estado do spoke, se necessário |

O provisionamento do spoke (descentralizado — `../network/03`) usa a role do lado Hub para
criar o `ResourceShare` e o attachment accepter na conta `network`, assumindo-a a partir da conta
de projeto. Sem IAM user duplicado no Hub.

## Nesta PoC (conta única) ainda não há cross-account

O PoC roda tudo numa conta só (`<account-id>`) — hub e spoke coincidem, então `AssumeRole`
cross-account **não é exercido ainda** e o código o suprime automaticamente (RAM share e
accepter viram no-op quando hub e spoke são a mesma conta — `../network/03`). As roles
cross-account entram quando o template de account (`../accounts/`) separar Hub e projeto em
contas distintas. Documentar aqui é o mapa, não o estado atual.

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **[SEC02-BP02](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_identities_unique.html)** credenciais temporárias | STS da conta de destino, sem IAM user duplicado |
| **[SEC03-BP08](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_permissions_share_securely.html)** confused deputy | `ExternalId` obrigatório para roles assumíveis por terceiros |
| **[SEC03-BP07](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_permissions_analyze_cross_account.html)** limitar acesso cross-account | trust policy escopada ao principal, não ao `root` da conta |

## Próximo

→ [`03-perimetro-de-dados-e-ram.md`](03-perimetro-de-dados-e-ram.md): resource policies e
RAM — o outro lado da fronteira cross-account.
