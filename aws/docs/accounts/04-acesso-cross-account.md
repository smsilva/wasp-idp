# 04 — Acesso Cross-Account

**Pilar WAF principal:** Security (SEC02 — gerenciamento de identidades; SEC03 — permissões).

## O problema: N contas, quantos usuários?

Sem um plano, cada conta nova significa criar usuários IAM de novo, senhas de novo, MFA de
novo — não escala e cada usuário IAM solto é uma credencial de longa duração a mais para
vazar. A resposta da AWS é **federar identidade uma vez, autorizar por conta**.

## IAM Identity Center (antigo AWS SSO)

Habilitado **uma vez**, na management account. A partir daí:

- **Uma identidade humana** (seu usuário no Identity Center, ou federado de um IdP externo
  — Okta, Azure AD, Google Workspace).
- **Permission Sets** — coleções de policies IAM reutilizáveis (ex.: `AdministratorAccess`,
  `ReadOnlyAccess`, um permission set custom `NetworkEngineer`).
- **Atribuições** — qual identidade tem qual permission set em qual conta. Uma pessoa pode
  ter `AdministratorAccess` na conta de projeto A e `ReadOnlyAccess` na conta network.

Login único (`aws sso login`) gera credenciais temporárias por conta — nada de access key de
longa duração para uso humano interativo.

## Fluxo de login (o que você já está fazendo nesta sessão)

```bash
aws sso login --profile <profile>
aws sts get-caller-identity --profile <profile>
# arn:aws:sts::<account-id>:assumed-role/AWSReservedSSO_<permission-set>_<hash>/<user>
```

O padrão `assumed-role/AWSReservedSSO_*` na identidade é a assinatura de que o acesso veio do
Identity Center, não de uma credencial IAM de longa duração — é o padrão desejado.

## Acesso automatizado (Crossplane, CI/CD) — não é humano, não usa SSO

Para automação (o Crossplane hospedado no hub k3d, por exemplo), o padrão é diferente:
**IAM user dedicado com policy escopada**, não SSO (SSO é para humanos com sessão
interativa). Ver `../../CLAUDE.md` para o padrão adotado nesta PoC — `crossplane-poc` é
esse exemplo concreto, incluindo o problema de bootstrap (a própria automação não pode se
auto-conceder IAM).

**Cross-account para automação:** quando a automação de uma conta precisa agir em outra
(ex.: o Hub compartilhando o TGW via RAM com a conta de projeto — `../network/03-transit-gateway-isolamento.md`),
o padrão é **IAM Role assumível cross-account** (`sts:AssumeRole` com trust policy
escopada à conta de origem), não um segundo IAM user duplicado na conta de destino.

## Acesso admin à conta-membro *antes* de o SSO estar propagado

Habilitar o Identity Center e atribuir permission sets é uma configuração à parte — logo
após `create-account`, a conta-membro nova normalmente **ainda não tem** atribuição SSO
própria, então `aws sso login` não a alcança. O gancho que **sempre** existe é a role
`OrganizationAccountAccessRole` (ver `03-provisionamento-de-contas.md`, passo ④), assumível
a partir da management account.

Em vez de `aws sts assume-role` avulso (credenciais temporárias soltas no shell), o padrão
reutilizável pela CLI é um **named profile** que a SDK renova sozinha a cada chamada:

```ini
# ~/.aws/config
[profile <member-alias>]
role_arn = arn:aws:iam::<member-account-id>:role/OrganizationAccountAccessRole
source_profile = <management-profile>   # profile SSO admin da management account
role_session_name = <session-name>
region = <region>
```

```bash
aws sso login --profile <management-profile>     # sessão da management ativa
AWS_PROFILE=<member-alias> aws sts get-caller-identity
# arn:aws:sts::<member-account-id>:assumed-role/OrganizationAccountAccessRole/<session-name>
```

O `assumed-role/OrganizationAccountAccessRole` na identidade confirma o hop cross-account.
Continua sendo credencial **temporária** (STS via role), sem access key de longa duração —
mesma propriedade do SSO. É acesso **de bootstrap**: serve até o permission set SSO da
conta-membro ser criado, quando o caminho passa a ser o `aws sso login` direto acima.

### Atalho interino no portal (enquanto o SSO não é atribuído)

No console web, a alternativa ao `aws sso login` é o **Switch role** (mesmo
`OrganizationAccountAccessRole`). Depois da primeira vez, o menu do canto superior direito
guarda a conta no histórico (1 clique). Dá para favoritar a URL direta:

```text
https://signin.aws.amazon.com/switchrole?account=<member-account-id>&roleName=OrganizationAccountAccessRole&displayName=<member-alias>&color=<hex>
```

É só um atalho — não substitui o permission set (a conta-membro continua **fora** do portal
SSO até receber a atribuição abaixo).

### Atribuir permission set SSO à conta-membro (elimina o switch role)

Passo que faz a conta-membro (ex.: `network`) aparecer no portal SSO e no `aws sso login`
direto, tanto no navegador quanto na CLI. Executar **uma vez** por conta:

```bash
scripts/assign-permission-set --account <conta> --group <grupo>
```

O script cria/reusa o permission set no Identity Center, resolve o principal no Identity
Store e cria a atribuição (idempotente nos três passos). Equivalente manual, na management
account → IAM Identity Center:

1. **Create permission set** → `AdministratorAccess` (managed) — ou um custom por função
   (ver convenção de nomenclatura abaixo).
2. **Assign** → conta-membro → seu usuário/grupo → esse permission set.
3. Depois disso, migrar o profile CLI de `role_arn`/`source_profile` (acima) para um bloco
   SSO nativo:
   ```ini
   [profile <member-alias>]
   sso_session = <sso-session>
   sso_account_id = <member-account-id>
   sso_role_name = AdministratorAccess
   region = <region>
   ```

Enquanto a atribuição não existir, o acesso admin à conta-membro é via named profile
(assume-role) + Switch role no portal — ambos descritos acima.

**`--group` em vez de `--user`.** A atribuição sobrevive a quem entra e sai do time; com
`--user`, cada pessoa nova exige uma atribuição nova em cada conta.

**Exceção da `log-archive`:** ali o permission set de rotina é `ReadOnlyAccess`, não
`AdministratorAccess` — o valor da conta vem de ninguém poder apagar o acervo
(`07-cloudtrail-e-log-archive.md`).

## Convenção de nomenclatura de permission sets

| Permission Set | Uso | Contas típicas |
|---|---|---|
| `AdministratorAccess` | Bootstrap, emergências, dono do projeto | todas, mas atribuição restrita a poucas pessoas |
| `<project>NetworkEngineer` | Operar rede do projeto (VPC, subnets, TGW attachment) | conta do projeto + Hub (leitura) |
| `ReadOnlyAccess` | Auditoria, observabilidade | todas |

Nomear por **função**, não por pessoa — o permission set sobrevive a quem entra/sai do time.

## Estado aplicado nesta Organization

Passo ⑦ parcialmente concluído. Instância do Identity Center e identity store: ver
`CLAUDE.local.md`.

| Item | Estado |
|---|---|
| Grupo `platform-admins` | criado, com o usuário admin da plataforma |
| Conta `log-archive` | `AdministratorAccess` atribuído a `platform-admins` |
| Contas `network`, `<projeto>-nonprod` | **sem** permission set — acesso ainda via `OrganizationAccountAccessRole` assumida da management account |

Conferir a qualquer momento com `scripts/show-permission-sets` (somente leitura).

Pendências conhecidas:

- **`log-archive` deveria ser `ReadOnlyAccess`, não `AdministratorAccess`.** O admin é
  bootstrap; mantido assim, quem é auditado pode apagar o acervo — anula o motivo de a conta
  existir. Trocar quando houver operação de rotina.
- Rodar `scripts/assign-permission-set --account <conta> --group platform-admins` para
  `network` e `<projeto>-nonprod`, eliminando o switch-role manual.

### Rebaixar uma conta de admin para leitura (reprodutível)

Não existe "update assignment" na API — são duas chamadas. **Atribuir o novo antes de revogar
o antigo** evita uma janela sem acesso:

```bash
scripts/assign-permission-set --account log-archive --group platform-admins \
  --permission-set ReadOnlyAccess \
  --managed-policy arn:aws:iam::aws/policy/ReadOnlyAccess

scripts/revoke-permission-set --account log-archive --group platform-admins \
  --permission-set AdministratorAccess

scripts/show-permission-sets --account log-archive   # confere
```

O `revoke` remove só a **atribuição** naquela conta — o permission set continua existindo
para as demais. Depois de qualquer mudança, `aws sso login` de novo para o cache local
refletir o novo acesso.

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **SEC02-BP01** identidade centralizada | Identity Center como fonte única, sem IAM user por conta |
| **SEC02-BP02** credenciais temporárias | Login SSO gera STS temporário, nunca access key de longa duração para humanos |
| **SEC03-BP01** menor privilégio por permission set | Escopar por função, não conceder `AdministratorAccess` por padrão |

## Próximo

→ [`05-billing-e-tags.md`](05-billing-e-tags.md): billing consolidado e tagging por projeto.
