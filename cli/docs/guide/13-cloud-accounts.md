# Cloud accounts

Uma cloud account é uma conta AWS em que a plataforma pode criar coisas (ADR 0029). A plataforma não guarda segredo por conta: ela assume uma role da conta a partir da credencial base do `init --aws-profile`. Qualquer usuário registra as próprias contas, sem aprovação; a posse é provada pela trust policy que só quem administra a conta consegue aplicar.

```bash
platform cloud account add nonprod-aws \
  --role-arn arn:aws:iam::123456789012:role/platform
```

```
✓ cloud account nonprod-aws added (pending)
Trust policy of arn:aws:iam::123456789012:role/platform:
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::<conta-da-plataforma>:user/<credencial-base>"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "<gerado pela API>"
        }
      }
    }
  ]
}
Apply it as the trust policy of the role, then run: platform cloud account verify nonprod-aws --wait
```

O ExternalId é gerado pela API, um por conta, e impede que alguém registre a role de outra pessoa. Aplique a policy na role (console ou `aws iam update-assume-role-policy --role-name platform --policy-document file://trust.json`) e peça a verificação:

```bash
platform cloud account verify nonprod-aws --wait

platform cloud account list
```

```
✓ nonprod-aws ready (account 123456789012)
NAME         VENDOR  ACCOUNT       STATUS  VALIDATED
nonprod-aws  aws     123456789012  ready   2026-10-11T12:00:00Z
```

O provider assume a role duas vezes: com o ExternalId tem que funcionar, e sem ele tem que falhar. Uma trust policy sem a condição de `sts:ExternalId` aceita qualquer ExternalId, e a conta fica em `ExternalIdNotEnforced`, nunca `ready`. Ele revalida a cada 6 horas, e enquanto a conta não está `ready` tenta de novo com intervalos crescentes, até 15 minutos.

| Status | Significado |
|---|---|
| `pending` | o provider ainda não verificou |
| `TrustNotEstablished` | a role não confia na plataforma com esse ExternalId; aplique a trust policy do `get` |
| `ExternalIdNotEnforced` | a role confia sem exigir o ExternalId; acrescente a condição |
| `AccountMismatch` | a role assumida está em outra conta |
| `VerificationFailed` | outro erro da AWS, na `message` (por exemplo, a credencial base expirou) |
| `ready` | a plataforma assume a role, e só com o ExternalId |

Cada conta é de quem a registrou: os outros usuários não a veem nem a removem (`403`), e `platform-admins` veem todas, com a coluna OWNER. A mesma role não é registrada duas vezes (`409`). Sem credencial base, o `add` responde `409` pedindo o `init --aws-profile`. Remover a conta tira o registro da plataforma; a role continua na conta AWS.
