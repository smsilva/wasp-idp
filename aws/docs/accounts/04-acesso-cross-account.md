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
  ter `AdministratorAccess` na conta de projeto A e `ReadOnlyAccess` na Hub account.

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

## Convenção de nomenclatura de permission sets

| Permission Set | Uso | Contas típicas |
|---|---|---|
| `AdministratorAccess` | Bootstrap, emergências, dono do projeto | todas, mas atribuição restrita a poucas pessoas |
| `<project>NetworkEngineer` | Operar rede do projeto (VPC, subnets, TGW attachment) | conta do projeto + Hub (leitura) |
| `ReadOnlyAccess` | Auditoria, observabilidade | todas |

Nomear por **função**, não por pessoa — o permission set sobrevive a quem entra/sai do time.

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **SEC02-BP01** identidade centralizada | Identity Center como fonte única, sem IAM user por conta |
| **SEC02-BP02** credenciais temporárias | Login SSO gera STS temporário, nunca access key de longa duração para humanos |
| **SEC03-BP01** menor privilégio por permission set | Escopar por função, não conceder `AdministratorAccess` por padrão |

## Próximo

→ [`05-billing-e-tags.md`](05-billing-e-tags.md): billing consolidado e tagging por projeto.
