# 04 — Cross-Account Access

**Pilar WAF principal:** Security ([SEC02 — Identity management](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/identity-management.html); [SEC03 — Permissions management](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/permissions-management.html)).

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

Para automação (o Crossplane hospedado no control plane k3d, por exemplo), o padrão é diferente:
**IAM user dedicado com policy escopada**, não SSO (SSO é para humanos com sessão
interativa). Ver `../../CLAUDE.md` para o padrão adotado nesta PoC — `crossplane-poc` é
esse exemplo concreto, incluindo o problema de bootstrap (a própria automação não pode se
auto-conceder IAM).

**Cross-account para automação:** quando a automação de uma conta precisa agir em outra
(ex.: o Hub compartilhando o TGW via RAM com a conta de projeto — `../network/03-transit-gateway-isolation.md`),
o padrão é **IAM Role assumível cross-account** (`sts:AssumeRole` com trust policy
escopada à conta de origem), não um segundo IAM user duplicado na conta de destino.

## Acesso admin à conta-membro *antes* de o SSO estar propagado

Habilitar o Identity Center e atribuir permission sets é uma configuração à parte — logo
após `create-account`, a conta-membro nova normalmente **ainda não tem** atribuição SSO
própria, então `aws sso login` não a alcança. O gancho que **sempre** existe é a role
`OrganizationAccountAccessRole` (ver `03-provisioning.md`, passo ④), assumível
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
(`07-cloudtrail-and-log-archive.md`).

## Convenção de nomenclatura de permission sets

| Permission Set | Uso | Contas típicas |
|---|---|---|
| `AdministratorAccess` | Bootstrap, emergências, dono do projeto | todas, mas atribuição restrita a poucas pessoas |
| `<project>NetworkEngineer` | Operar rede do projeto (VPC, subnets, TGW attachment) | conta do projeto + `network` (leitura) |
| `ReadOnlyAccess` | Auditoria, observabilidade | todas |

Nomear por **função**, não por pessoa — o permission set sobrevive a quem entra/sai do time.

## Estado aplicado nesta Organization

Passo ⑦ parcialmente concluído. Instância do Identity Center e identity store: ver
`CLAUDE.local.md`.

| Item | Estado |
|---|---|
| Permission sets existentes | `AdministratorAccess`, `ReadOnlyAccess` |
| Grupo `platform-admins` | criado, com o usuário admin da plataforma |
| Management account | `AdministratorAccess` atribuído **ao usuário**, não ao grupo |
| Conta `log-archive` | ✅ `ReadOnlyAccess` atribuído a `platform-admins` — já rebaixado do admin de bootstrap |
| Contas `network`, `<projeto>-nonprod` | **sem** permission set — acesso ainda via `OrganizationAccountAccessRole` assumida da management account |

Conferir a qualquer momento com `scripts/show-permission-sets` (somente leitura) — é a fonte
de verdade; esta tabela é retrato datado.

Pendências conhecidas:

- **Management account atribuída a usuário, não a grupo.** Contraria a regra `--group` acima,
  e é justamente a conta onde a atribuição mais importa. Migrar para `platform-admins`
  (atribuir o grupo antes de revogar o usuário).
- Rodar `scripts/assign-permission-set --account <conta> --group platform-admins` para
  `network` e `<projeto>-nonprod`, eliminando o switch-role manual.

### Rebaixar uma conta de admin para leitura (reprodutível)

Não existe "update assignment" na API — são duas chamadas. **Atribuir o novo antes de revogar
o antigo** evita uma janela sem acesso. A sequência abaixo já foi executada na `log-archive`
(hoje `ReadOnlyAccess`); fica registrada como receita para as próximas contas:

```bash
scripts/assign-permission-set --account log-archive --group platform-admins \
  --permission-set ReadOnlyAccess \
  --managed-policy arn:aws:iam::aws:policy/ReadOnlyAccess

scripts/revoke-permission-set --account log-archive --group platform-admins \
  --permission-set AdministratorAccess

scripts/show-permission-sets --account log-archive   # confere
```

O `revoke` remove só a **atribuição** naquela conta — o permission set continua existindo
para as demais. Depois de qualquer mudança, `aws sso login` de novo para o cache local
refletir o novo acesso.

## Break-glass: acesso de emergência ([SEC03-BP03 — Establish emergency access process](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_permissions_emergency_process.html))

O caminho normal — Identity Center → permission set → STS — tem modos de falha que ele
próprio não resolve: o Identity Center indisponível na região, a última atribuição de admin
revogada por engano, um SCP que fecha a porta da própria operação. Sem um caminho alternativo
**definido antes da emergência**, a saída improvisada é sempre a mesma: o root da conta. Que é
exatamente o que o passo ⑦ existe para evitar.

### Os dois caminhos, em ordem de preferência

| # | Caminho | Alcança | Quando usar |
|---|---|---|---|
| 1 | `OrganizationAccountAccessRole` assumida da management account (named profile, acima) | Qualquer conta-membro | Perda de acesso a **uma** conta-membro. Cobre a maioria dos casos |
| 2 | **Root user da conta afetada** | A própria conta, sem limite de SCP | Só quando (1) não serve: management account inacessível, Identity Center fora, ou ação que exige root (fechar conta, alterar e-mail de root, remover política do S3 que bloqueou todo mundo) |

O caminho 1 **não é** break-glass de verdade — depende da management account estar acessível.
É o degrau intermediário que evita chegar ao root na maioria dos incidentes.

### Regras do caminho 2 (root)

1. **Credencial não fica com uma pessoa.** Senha e MFA do root de cada conta-membro ficam em
   custódia (cofre corporativo), separadas — quem tem a senha não tem o dispositivo MFA.
2. **MFA obrigatório**, preferencialmente hardware ([SEC01-BP02 — Secure account root user and properties](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_securely_operate_aws_account.html)).
3. **Zero access key de root.** A conta não deve ter nenhuma; se tiver, apagar.
4. **Uso é evento auditável, não operação.** Todo uso gera registro: quem, quando, por quê,
   o que foi feito, e qual foi a correção que tornou o root desnecessário de novo.
5. **Rotação depois do uso.** Senha trocada e devolvida à custódia ao fechar o incidente.
6. **Ensaio periódico.** Um caminho de emergência nunca exercitado é indistinguível de um
   caminho quebrado. Validar em janela planejada, não durante o incidente.

### Detecção

O CloudTrail organizacional (`07-cloudtrail-and-log-archive.md`) já captura `userIdentity.type
= Root` em toda a Organization — o acervo existe. Falta o **alarme**: uso de root sem alerta
é auditoria post-mortem, não controle detectivo.

### Estado nesta Organization

| Item | Estado |
|---|---|
| Caminho 1 (`OrganizationAccountAccessRole`) | ✅ funciona — é o acesso corrente às contas sem permission set |
| MFA no root da management account | ⚠️ verificar |
| MFA no root das contas-membro | ⚠️ verificar — contas criadas por `create-account` nascem sem |
| Custódia separada de senha/MFA | ❌ não implementado (conta pessoal, operador único) |
| Alarme de uso de root | ❌ não implementado |
| Ensaio | ❌ nunca executado |

> Numa Organization de operador único, "custódia separada" não tem contraparte — mas MFA no
> root e alarme de uso valem igual, e são os dois itens de menor custo da lista.

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **[SEC01-BP02 — Secure account root user and properties](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_securely_operate_aws_account.html)** | Root de cada conta-membro nunca é usado na rotina; o caminho normal é o permission set |
| **[SEC02-BP01 — Use strong sign-in mechanisms](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_identities_enforce_mechanisms.html)** | MFA no Identity Center como porta de entrada única para humanos |
| **[SEC02-BP02 — Use temporary credentials](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_identities_unique.html)** | Login SSO gera STS temporário, nunca access key de longa duração para humanos |
| **[SEC02-BP04 — Rely on a centralized identity provider](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_identities_identity_provider.html)** | Identity Center como fonte única, sem IAM user por conta |
| **[SEC02-BP06 — Employ user groups and attributes](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_identities_groups_attributes.html)** | Atribuição a `--group`, não a `--user` |
| **[SEC03-BP01 — Define access requirements](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_permissions_define.html)** | Permission set nomeado por função (`<project>NetworkEngineer`), não por pessoa |
| **[SEC03-BP02 — Grant least privilege access](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_permissions_least_privileges.html)** | `ReadOnlyAccess` onde a rotina é leitura (ex.: `log-archive`), não `AdministratorAccess` por padrão |
| **[SEC03-BP03 — Establish emergency access process](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_permissions_emergency_process.html)** | Break-glass documentado abaixo |
| **[SEC03-BP04 — Reduce permissions continuously](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_permissions_continuous_reduction.html)** | Rebaixamento reprodutível (`assign` novo → `revoke` antigo), acima |
| **[SEC03-BP06 — Manage access based on lifecycle](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_permissions_lifecycle.html)** | Atribuição por grupo sobrevive a quem entra/sai do time |

IDs conferidos contra [SEC02 — Identity management](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/identity-management.html)
e [SEC03 — Permissions management](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/permissions-management.html).

## Próximo

→ [`05-billing-and-tags.md`](05-billing-and-tags.md): billing consolidado e tagging por projeto.
