# 03 — Provisionamento de Contas

**Pilar WAF principal:** Operational Excellence (repetibilidade — criar conta é uma operação
de rotina, não um evento especial).

## Criar uma conta programaticamente

```bash
aws organizations create-account \
  --email "<account-alias>+aws@<root-domain>" \
  --account-name "<account-alias>"
```

- `create-account` é **assíncrono** — retorna um `CreateAccountRequestId`; a conta leva de
  segundos a poucos minutos para ficar `SUCCEEDED`. Poll com:
  ```bash
  aws organizations describe-create-account-status \
    --create-account-request-id <request-id>
  ```
- **O e-mail precisa ser único em toda a AWS** (não só na sua Organization) — nenhuma conta
  AWS, de ninguém, pode já ter usado aquele e-mail. E precisa ser **válido e controlado por
  você**: ele vira o usuário **root** da conta, e é para onde a AWS manda verificação e reset
  de senha. Um domínio fictício (`example.com`) cria a conta mas te deixa **sem acesso ao
  root** — evite fora de testes descartáveis.

### Dois modos de plus-addressing (o script `scripts/create-account` cobre ambos)

O truque do "+" gera e-mails únicos por conta a partir de uma única caixa: a AWS trata
`caixa+tag@dominio` como endereço distinto, mas o provedor entrega tudo na mesma caixa,
**ignorando o que vem depois do `+`**. Como o nome da conta entra na composição muda entre
os dois modos:

- **Domínio corporativo com catch-all** (ex.: `<email-domain>`): o nome da conta vira a *base* e
  `aws` é o tag fixo → `<name>+aws@<domain>`, ex.: `hub+aws@<email-domain>`. Funciona porque o
  catch-all do domínio roteia qualquer base para a caixa certa. É o **default** do script
  (sem `--email-user`).

- **Caixa pessoal Gmail/Workspace** (ex.: `smsilva@gmail.com`): você **não** controla o
  domínio, então a base tem de ser a sua caixa e o nome da conta vira o *tag* →
  `<email-user>+<name>@<domain>`, ex.: `smsilva+hub@gmail.com`. Passe `--email-user smsilva`.
  ⚠️ Não use `<name>+aws@gmail.com` aqui: o Gmail entregaria em `<name>@gmail.com` (uma caixa
  que não é a sua) — nunca chega em você. Validado em execução real: com
  `--email-user smsilva`, o e-mail "Your Amazon Web Services Account is Ready" chegou em
  `smsilva@gmail.com` endereçado a `smsilva+hub` — a prova de que o root da conta é acessível.

```bash
# catch-all corporativo (default):
scripts/create-account --name hub --email-domain <email-domain> --ou infra
#   -> hub+aws@<email-domain>

# Gmail/Workspace pessoal:
scripts/create-account --name hub --email-user smsilva --email-domain gmail.com --ou infra
#   -> smsilva+hub@gmail.com
```

## Mover a conta para a OU correta

`create-account` cria a conta sob a **Root** da Organization — mover para a OU explicitamente:

```bash
aws organizations move-account \
  --account-id <account-id> \
  --source-parent-id <root-id> \
  --destination-parent-id <ou-id>
```

Hub account → OU Infra. Conta de projeto → OU Workloads (tópico 1).

> **Gotcha (descoberto em execução real):** `create-account` cria a conta sob a **Root**, então
> o `move-account` tem de mirar a **OU de destino**, nunca a própria Root. Mover a conta da Root
> para a Root retorna `DuplicateAccountException` ("already present at the specified
> destination"). Para o Hub isso significa buscar o ID da OU **Infra** (filha da Root) —
> `--query "OrganizationalUnits[?Name=='Infra'].Id"` — e não reusar `root_id` como atalho.
> Como o `move-account` roda **depois** de a conta já ter sido criada, o script é **idempotente**:
> re-executar detecta a conta ACTIVE existente e só refaz o move para a OU correta.

## O papel do root da conta-membro nova

Toda conta criada via `create-account` nasce com um usuário **root** próprio (a senha não é
definida automaticamente — requer fluxo de "esqueci a senha" se for necessário logar como
root). Na prática, **você nunca deveria precisar logar como root** numa conta-membro: o
acesso do dia a dia é via **IAM Identity Center / SSO** (tópico 4), que já provê uma role
administrativa sem precisar do root.

**Quando o root é inevitável:** certas ações só o root pode fazer (ex.: fechar a conta,
alterar o e-mail raiz, sair de suporte enterprise). São raras e conhecidas — não bloqueiam o
fluxo normal de provisionamento.

## Bootstrap de acesso administrativo na conta nova

Toda conta criada dentro de uma Organization com `feature-set ALL` automaticamente ganha uma
role `OrganizationAccountAccessRole` (assumível a partir da management account) — é o gancho
inicial para configurar o SSO (tópico 4) sem precisar do root.

```bash
aws sts assume-role \
  --role-arn arn:aws:iam::<new-account-id>:role/OrganizationAccountAccessRole \
  --role-session-name bootstrap
```

> Para uso recorrente na CLI (não só uma verificação avulsa), prefira encapsular esse
> assume-role num **named profile** (`role_arn` + `source_profile`) em vez de exportar as
> credenciais STS à mão — a SDK renova a sessão sozinha. Padrão em
> [`04-acesso-cross-account.md`](04-acesso-cross-account.md#acesso-admin-à-conta-membro-antes-de-o-sso-estar-propagado).
> É o caminho de acesso admin à conta-membro **enquanto** o permission set SSO dela não foi
> criado (passo ⑤).

## Checklist de uma conta nova, do zero ao "pronta para workload"

```text
① create-account (com e-mail único)
② poll até SUCCEEDED
③ move-account para a OU correta (Infra ou Workloads)
④ assume-role OrganizationAccountAccessRole (verificação de acesso)
⑤ Configurar permission set do SSO para a conta (tópico 4)
⑥ SCPs da OU já se aplicam automaticamente (herdadas — tópico 2, nada a fazer aqui)
⑦ Conta pronta — segue para `../network/` provisionar a spoke, se for conta de projeto
```

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **OPS** repetibilidade | Sequência é a mesma para toda conta nova — script, não ritual manual |
| **SEC01** minimizar uso de root | `OrganizationAccountAccessRole` + SSO evitam qualquer necessidade de login root |

## Próximo

→ [`04-acesso-cross-account.md`](04-acesso-cross-account.md): como o time acessa múltiplas
contas sem multiplicar usuários IAM.