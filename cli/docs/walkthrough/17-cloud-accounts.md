# Cloud accounts

**Só com a credencial base:** rode o `init` uma vez com um profile do `~/.aws` (o `init` lembra a credencial nas execuções seguintes). Use um **IAM user dedicado**, com permissão só para `sts:AssumeRole` e `sts:GetCallerIdentity`; com SSO, o `init` avisa quando a credencial expira.

```bash
platform init \
  --target local \
  --aws-profile <profile-da-plataforma>
```

``` { .text .output title="saída" }
…
deploying the cloud account provider (aws_account) …
✓ cloud accounts verified by the aws_account provider
```

Registre uma conta pela **role que a plataforma vai assumir** nela:

```bash
platform cloud account add demo-aws \
  --role-arn arn:aws:iam::<conta>:role/platform
```

``` { .text .output title="saída" }
✓ cloud account demo-aws added (pending)
Trust policy of arn:aws:iam::<conta>:role/platform:
{ … "sts:ExternalId": "<gerado pela API>" … }
Apply it as the trust policy of the role, then run: platform cloud account verify demo-aws --wait
```

Antes de aplicar a policy, a conta fica em `TrustNotEstablished`. Grave a policy do `get --output json` num arquivo e aplique-a na role.

!!! step "Aplicar a trust policy na role"

    No lado da conta, com o profile de quem a administra:

    ```bash
    platform cloud account get demo-aws \
      --output json \
      | jq .trustPolicy > /tmp/trust.json

    aws iam update-assume-role-policy \
      --role-name platform \
      --policy-document file:///tmp/trust.json \
      --profile <admin-da-conta>
    ```

!!! step "Verificar"

    ```bash
    platform cloud account verify demo-aws \
      --wait

    platform cloud account list
    ```

    ``` { .text .output title="saída" }
    ✓ demo-aws ready (account <conta>)
    NAME      VENDOR  ACCOUNT  STATUS  VALIDATED            OWNER
    demo-aws  aws     <conta>  ready   2026-10-11T12:00:00Z voce@example.com
    ```

Tire a condição `sts:ExternalId` da policy e rode o `verify --wait` de novo: a conta vai para `ExternalIdNotEnforced`, porque sem a condição qualquer um que conheça a role e confie na mesma credencial base a registraria. Volte a policy original e remova a conta:

```bash
platform cloud account remove demo-aws
```

``` { .text .output title="saída" }
✓ cloud account demo-aws removed
```
